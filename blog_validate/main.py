import json
from pathlib import Path
from typing import Optional
import typer
from typing import Annotated
from rich.console import Console
from rich.table import Table
from rich import box
from blog_validate.config import load_config, resolve_content_root
from blog_validate.env import setup_environment
from blog_validate.extractor import PostBlocks, scan_posts, build_fixture_registry, scan_helpers_dir
from blog_validate.languages.base import AnnotationType
from blog_validate.runner import (
    PostResult,
    get_changed_files,
    resolve_changed_posts,
    run_post,
)
from blog_validate.inspector import analyze_post, format_guide, _has_assert_statements

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")

ConfigOption = Annotated[
    Optional[str],
    typer.Option("--config", help="Path to an alternate blog-validate.toml"),
]


def _load_posts(config_path: str | None):
    """Load the config (explicit path or walk-up from cwd) and scan its posts."""
    config = load_config(Path.cwd(), Path(config_path) if config_path else None)
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )
    return config, all_post_blocks


def _code_preview(code: str, max_lines: int = 3) -> str:
    lines = code.strip().splitlines()
    preview = "\n".join(f"    {line}" for line in lines[:max_lines])
    if len(lines) > max_lines:
        preview += "\n    ..."
    return preview


def _lang_cell(results: list, lang: str) -> str:
    blocks = [r for r in results if r.block.language == lang]
    if not blocks:
        return ""
    passed = sum(1 for r in blocks if r.status == "passed")
    failed = sum(1 for r in blocks if r.status == "failed")
    skipped = sum(1 for r in blocks if r.status == "skipped")
    parts = []
    if passed:
        parts.append(f"[green]{passed}✓[/green]")
    if failed:
        parts.append(f"[red]{failed}✗[/red]")
    if skipped:
        parts.append(f"[dim]{skipped}–[/dim]")
    return " ".join(parts)


def _print_results(results: list[PostResult], verbose: bool) -> bool:
    """Print results as a Rich table. Returns True if any post failed."""
    console = Console()

    # Determine which languages appear across all results
    all_langs: list[str] = []
    seen: set[str] = set()
    lang_order = ["python", "sql", "bash", "shell", "markdown", "toml"]
    for post_result in results:
        for r in post_result.results:
            if r.block.language not in seen:
                seen.add(r.block.language)
    for lang in lang_order:
        if lang in seen:
            all_langs.append(lang)
    for lang in sorted(seen - set(lang_order)):
        all_langs.append(lang)

    table = Table(box=box.SIMPLE_HEAD, show_footer=False, pad_edge=False)
    table.add_column("Post", style="bold", min_width=30, no_wrap=True)
    table.add_column("Status", justify="center", min_width=6)
    table.add_column("pass", justify="right", min_width=4)
    table.add_column("fail", justify="right", min_width=4)
    table.add_column("skip", justify="right", min_width=4)
    for lang in all_langs:
        table.add_column(lang, justify="center", min_width=max(4, len(lang)))

    any_failed = False
    detail_posts: list[tuple[str, list, bool]] = []  # (slug, block_results, post_passed)

    for post_result in results:
        status_str = "[green]PASS[/green]" if post_result.passed else "[red]FAIL[/red]"
        lang_cells = [_lang_cell(post_result.results, lang) for lang in all_langs]
        table.add_row(
            post_result.slug,
            status_str,
            str(post_result.passed_count) if post_result.passed_count else "[dim]0[/dim]",
            f"[red]{post_result.failed_count}[/red]" if post_result.failed_count else "[dim]0[/dim]",
            f"[dim]{post_result.skipped_count}[/dim]" if post_result.skipped_count else "[dim]0[/dim]",
            *lang_cells,
        )
        if not post_result.passed:
            any_failed = True
        if not post_result.passed or verbose:
            detail_posts.append((post_result.slug, post_result.results, post_result.passed))

    console.print(table)

    # Print per-block details: always for failing posts, plus all posts when --verbose
    for slug, block_results, post_passed in detail_posts:
        if not post_passed:
            console.print(f"[red bold]FAIL[/red bold] [bold]{slug}[/bold]")
        elif verbose:
            console.print(f"[green bold]PASS[/green bold] [bold]{slug}[/bold]")
        for r in block_results:
            if r.status == "failed":
                console.print(
                    f"  [red]✗[/red] block {r.block.block_index} [dim]({r.block.language})[/dim]: {r.error}"
                )
                if r.detail:
                    for line in r.detail.splitlines():
                        console.print(f"    [yellow]{line}[/yellow]")
                console.print(f"[dim]{_code_preview(r.block.code)}[/dim]")
                if r.hint:
                    console.print(f"  [cyan]Hint:[/cyan] {r.hint}")
                if r.stdout and (verbose or r.detail is None):
                    console.print("  [dim]Stdout:[/dim]")
                    for line in r.stdout.strip().splitlines()[-10:]:
                        console.print(f"    [dim]{line}[/dim]")
            elif verbose and r.status == "passed":
                console.print(
                    f"  [green]✓[/green] block {r.block.block_index} [dim]({r.block.language})[/dim]"
                )
                if r.stdout:
                    console.print("  [dim]Stdout:[/dim]")
                    for line in r.stdout.strip().splitlines()[-10:]:
                        console.print(f"    [dim]{line}[/dim]")

    return any_failed


@app.command()
def check(
    all_posts: Annotated[
        bool, typer.Option("--all", help="Validate all posts")
    ] = False,
    changed: Annotated[
        bool,
        typer.Option("--changed", help="Validate changed posts and fixture dependents"),
    ] = False,
    post: Annotated[
        Optional[str], typer.Option("--post", help="Validate a single post by slug")
    ] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n")] = False,
    config_path: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to an alternate blog-validate.toml"),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", "-j", help="Emit machine-readable JSON instead of the table")
    ] = False,
) -> None:
    """Validate code blocks in blog posts."""
    if not any([all_posts, changed, post]):
        typer.echo("Error: specify --all, --changed, or --post <slug>", err=True)
        raise typer.Exit(code=1)

    config = load_config(Path.cwd(), Path(config_path) if config_path else None)
    setup_environment(config.root, config.python.dependencies, config.python.venv)

    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )
    base_blocks, helper_fixtures = scan_helpers_dir(config.root, config.blog.helpers_path)
    # Post-level fixtures take precedence over helper fixtures on name collision
    fixture_registry = {**helper_fixtures, **build_fixture_registry(all_post_blocks)}

    if all_posts:
        posts_to_check = all_post_blocks
    elif changed:
        changed_files = get_changed_files(config.root)
        posts_to_check = resolve_changed_posts(
            changed_files,
            all_post_blocks,
            fixture_registry,
            config.root,
            config.blog.content_path,
            config.blog.post_file,
            config.blog.layout,
        )
    else:
        posts_to_check = [p for p in all_post_blocks if p.slug == post]
        if not posts_to_check:
            typer.echo(f"Error: post {post!r} not found", err=True)
            raise typer.Exit(code=1)

    # --post names one post explicitly, so it runs whatever its status.
    skipped_by_status: list[PostBlocks] = []
    if not post:
        posts_to_check, skipped_by_status = _split_by_status(posts_to_check, config.blog.skip_statuses)

    content_root = resolve_content_root(config.root, config.blog.content_path)

    if not posts_to_check:
        if as_json:
            typer.echo(json.dumps(_results_payload([], content_root, skipped_by_status), indent=2))
        else:
            typer.echo("No posts to validate.")
        raise typer.Exit(code=0)

    # Helper/setup warnings from run_post go to stderr in JSON mode so stdout
    # stays parseable.
    print_fn = (lambda s: typer.echo(s, err=True)) if as_json else print
    results = [
        run_post(
            p,
            fixture_registry,
            base_blocks=base_blocks or None,
            dry_run=dry_run,
            verbose=verbose,
            print_fn=print_fn,
            bash_execute=config.bash.execute,
        )
        for p in posts_to_check
    ]

    if as_json:
        typer.echo(json.dumps(_results_payload(results, content_root, skipped_by_status), indent=2))
        any_failed = any(not r.passed for r in results)
    else:
        any_failed = _print_results(results, verbose)
        passed = sum(1 for r in results if r.passed)
        typer.echo(f"\nDone. {passed}/{len(results)} posts passed.")
        if skipped_by_status:
            typer.echo(f"Not run (status {_status_breakdown(skipped_by_status)}): {len(skipped_by_status)} posts.")

    if any_failed:
        raise typer.Exit(code=1)


def _split_by_status(posts: list[PostBlocks], skip_statuses: list[str]) -> tuple[list[PostBlocks], list[PostBlocks]]:
    """Split posts into (to run, skipped because their frontmatter status is in skip_statuses)."""
    skip = set(skip_statuses)
    return (
        [p for p in posts if p.status not in skip],
        [p for p in posts if p.status in skip],
    )


def _status_breakdown(posts: list[PostBlocks]) -> str:
    counts: dict[str, int] = {}
    for p in posts:
        counts[p.status] = counts.get(p.status, 0) + 1
    return ", ".join(f"{s}: {n}" for s, n in sorted(counts.items()))


def _results_payload(
    results: list[PostResult], content_root: Path, skipped_by_status: list[PostBlocks] | None = None
) -> dict:
    """Shape `check` results for --json: one entry per post, every block's status."""
    skipped_by_status = skipped_by_status or []
    return {
        "content_root": str(content_root),
        "summary": {
            "posts": len(results),
            "posts_passed": sum(1 for r in results if r.passed),
            "posts_failed": sum(1 for r in results if not r.passed),
            "blocks_passed": sum(r.passed_count for r in results),
            "blocks_failed": sum(r.failed_count for r in results),
            "blocks_skipped": sum(r.skipped_count for r in results),
            "posts_skipped_by_status": len(skipped_by_status),
        },
        "skipped_by_status": [{"slug": p.slug, "status": p.status} for p in skipped_by_status],
        "posts": [
            {
                "slug": pr.slug,
                "passed": pr.passed,
                "counts": {
                    "passed": pr.passed_count,
                    "failed": pr.failed_count,
                    "skipped": pr.skipped_count,
                },
                "blocks": [
                    {
                        "index": r.block.block_index,
                        "language": r.block.language,
                        "annotation": r.block.annotation.value,
                        "status": r.status,
                        "error": r.error,
                        "hint": r.hint,
                    }
                    for r in pr.results
                ],
            }
            for pr in results
        ],
    }


@app.command("coverage")
def coverage(
    unannotated_only: Annotated[
        bool, typer.Option("--unannotated", help="List only posts with unannotated blocks")
    ] = False,
    show_all: Annotated[
        bool, typer.Option("--all", help="Include posts with no code blocks")
    ] = False,
    config_path: Annotated[
        Optional[str],
        typer.Option("--config", help="Path to an alternate blog-validate.toml"),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", "-j", help="Emit machine-readable JSON instead of the report")
    ] = False,
) -> None:
    """Report annotation coverage across all posts."""
    config = load_config(Path.cwd(), Path(config_path) if config_path else None)
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )
    all_post_blocks, skipped_by_status = _split_by_status(all_post_blocks, config.blog.skip_statuses)
    cov = _coverage_summary(all_post_blocks)
    cov["posts_skipped_by_status"] = len(skipped_by_status)

    if as_json:
        cov["content_root"] = str(resolve_content_root(config.root, config.blog.content_path))
        typer.echo(json.dumps(cov, indent=2))
        return

    typer.echo("Coverage report")
    typer.echo("─" * 47)
    if show_all or cov["no_blocks"] == 0:
        typer.echo(f"Posts with no code blocks:          {cov['no_blocks']:2}  (skipped — nothing to annotate)")
    typer.echo(f"Posts with only annotated blocks:   {cov['fully_covered']:2}  (fully covered)")
    typer.echo(f"Posts with unannotated blocks:      {cov['needs_attention']:2}  (needs attention)")

    if cov["unannotated_posts"]:
        typer.echo("\nUnannotated posts:")
        for entry in cov["unannotated_posts"]:
            noun = "block" if entry["count"] == 1 else "blocks"
            typer.echo(f"  {entry['slug']:50} {entry['count']} unannotated {noun}")

    if not unannotated_only and cov["skip_counts"]:
        typer.echo("\nSkipped blocks by reason:")
        for reason, count in sorted(cov["skip_counts"].items()):
            typer.echo(f"  {reason:20} {count:2}")

    if not unannotated_only and cov["executed_blocks"]:
        typer.echo(
            f"\nAssertion effectiveness: {cov['asserted_blocks']}/{cov['executed_blocks']} "
            f"executed blocks assert output  ({cov['assertion_pct']}%)"
        )
        if cov["unverified_posts"]:
            typer.echo("Posts with unverified blocks:")
            for entry in cov["unverified_posts"]:
                noun = "block" if entry["gap"] == 1 else "blocks"
                typer.echo(f"  {entry['slug']:50} {entry['gap']} unverified {noun}")


def _coverage_summary(all_post_blocks) -> dict:
    """Annotation coverage and assertion effectiveness, as plain data so the
    report and --json share one computation."""
    _EXECUTED = {AnnotationType.DEFAULT, AnnotationType.SETUP, AnnotationType.ASSERT}

    no_blocks = 0
    fully_covered = 0
    needs_attention = 0
    unannotated_posts: list[dict] = []
    skip_counts: dict[str, int] = {}
    post_effectiveness: list[tuple[str, int, int]] = []  # (slug, asserted, executed)

    for post in all_post_blocks:
        if not post.blocks:
            no_blocks += 1
            continue

        unannotated_count = sum(
            1 for b in post.blocks if b.annotation == AnnotationType.DEFAULT
        )
        for b in post.blocks:
            if b.annotation != AnnotationType.DEFAULT:
                skip_counts[b.annotation.value] = skip_counts.get(b.annotation.value, 0) + 1

        if unannotated_count > 0:
            needs_attention += 1
            unannotated_posts.append({"slug": post.slug, "count": unannotated_count})
        else:
            fully_covered += 1

        executed = [b for b in post.blocks if b.annotation in _EXECUTED]
        asserted = sum(
            1 for b in executed
            if b.annotation == AnnotationType.ASSERT or _has_assert_statements(b.code)
        )
        if executed:
            post_effectiveness.append((post.slug, asserted, len(executed)))

    total_asserted = sum(a for _, a, _ in post_effectiveness)
    total_executed = sum(e for _, _, e in post_effectiveness)
    unverified = sorted(
        ({"slug": s, "gap": e - a} for s, a, e in post_effectiveness if a < e),
        key=lambda x: -x["gap"],
    )
    return {
        "posts": len(all_post_blocks),
        "no_blocks": no_blocks,
        "fully_covered": fully_covered,
        "needs_attention": needs_attention,
        "unannotated_posts": unannotated_posts,
        "skip_counts": skip_counts,
        "asserted_blocks": total_asserted,
        "executed_blocks": total_executed,
        "assertion_pct": int(100 * total_asserted / total_executed) if total_executed else 0,
        "unverified_posts": unverified,
    }


@app.command("list-fixtures")
def list_fixtures(config_path: ConfigOption = None) -> None:
    """Show all named fixtures and the posts that define and use them."""
    config, all_post_blocks = _load_posts(config_path)
    fixture_registry = build_fixture_registry(all_post_blocks)

    if not fixture_registry:
        typer.echo("No named fixtures found.")
        return

    uses: dict[str, list[str]] = {name: [] for name in fixture_registry}
    for post in all_post_blocks:
        for b in post.blocks:
            if b.annotation == AnnotationType.USE and b.fixture_name in uses:
                uses[b.fixture_name].append(post.slug)

    for name, fixture_block in sorted(fixture_registry.items()):
        user_list = ", ".join(uses[name]) if uses[name] else "none"
        typer.echo(
            f"{name} ({fixture_block.language}) — defined in: {fixture_block.post_slug}"
        )
        typer.echo(f"  used by: {user_list}")


@app.command("list-posts")
def list_posts(config_path: ConfigOption = None) -> None:
    """Show all posts with code blocks and their annotation counts."""
    config, all_post_blocks = _load_posts(config_path)

    if not all_post_blocks:
        typer.echo("No posts with code blocks found.")
        return

    for post in all_post_blocks:
        counts: dict[str, int] = {}
        for b in post.blocks:
            counts[b.annotation.value] = counts.get(b.annotation.value, 0) + 1
        counts_str = ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))
        noun = "block" if len(post.blocks) == 1 else "blocks"
        typer.echo(f"{post.slug}: {len(post.blocks)} {noun} ({counts_str})")


@app.command("list-skips")
def list_skips(config_path: ConfigOption = None) -> None:
    """Show all skipped blocks with a code preview."""
    config, all_post_blocks = _load_posts(config_path)

    total = 0
    for post in all_post_blocks:
        for b in post.blocks:
            if b.annotation == AnnotationType.SKIP:
                total += 1
                typer.echo(f"{post.slug}  block {b.block_index} ({b.language})")
                typer.echo(_code_preview(b.code))
                typer.echo()

    typer.echo(f"Total: {total} skipped blocks")


@app.command("test-guide")
def test_guide(
    post: Annotated[
        Optional[str], typer.Option("--post", help="Post slug to inspect")
    ] = None,
    all_posts: Annotated[
        bool, typer.Option("--all", help="Show guide for all posts with code blocks")
    ] = False,
    config_path: ConfigOption = None,
) -> None:
    """Show a testing checklist for a post without executing any code."""
    if not post and not all_posts:
        typer.echo("Error: specify --post <slug> or --all", err=True)
        raise typer.Exit(code=1)

    config, all_post_blocks = _load_posts(config_path)

    if all_posts:
        targets = [p for p in all_post_blocks if p.blocks]
    else:
        targets = [p for p in all_post_blocks if p.slug == post]
        if not targets:
            typer.echo(f"Error: post {post!r} not found", err=True)
            raise typer.Exit(code=1)

    for i, p in enumerate(targets):
        if i > 0:
            typer.echo("")
        insight = analyze_post(p)
        typer.echo(format_guide(insight))


@app.command("stats")
def stats(config_path: ConfigOption = None) -> None:
    """Show block count by language across all posts."""
    config, all_post_blocks = _load_posts(config_path)

    lang_counts: dict[str, int] = {}
    total_blocks = 0
    total_posts = 0

    for post in all_post_blocks:
        if not post.blocks:
            continue
        total_posts += 1
        for b in post.blocks:
            lang = b.language or "(unlabeled)"
            lang_counts[lang] = lang_counts.get(lang, 0) + 1
            total_blocks += 1

    if not lang_counts:
        typer.echo("No code blocks found.")
        return

    console = Console()
    table = Table(box=box.SIMPLE_HEAD, show_footer=False)
    table.add_column("Language", style="cyan")
    table.add_column("Blocks", justify="right")
    table.add_column("Share", justify="right")

    for lang, count in sorted(lang_counts.items(), key=lambda x: -x[1]):
        pct = int(100 * count / total_blocks) if total_blocks else 0
        table.add_row(lang, str(count), f"{pct}%")

    console.print("\nBlock language distribution")
    console.print("─" * 47)
    console.print(table)
    typer.echo(f"Total: {total_blocks} blocks across {total_posts} posts")


@app.command("find")
def find_language(
    language: Annotated[str, typer.Argument(help="Language to search for (e.g. python, sql)")],
    count: Annotated[
        bool, typer.Option("--count/--no-count", "-c", help="Show block count per post")
    ] = True,
    config_path: ConfigOption = None,
) -> None:
    """List posts that contain blocks of a given language."""
    config, all_post_blocks = _load_posts(config_path)

    target = language.lower()
    matches: list[tuple[str, int]] = []

    for post in all_post_blocks:
        n = sum(
            1 for b in post.blocks
            if (b.language or "(unlabeled)").lower() == target
        )
        if n:
            matches.append((post.slug, n))

    if not matches:
        typer.echo(f"No posts found with {language!r} blocks.")
        return

    typer.echo(f"\nPosts containing {language!r} blocks")
    typer.echo("─" * 47)
    for slug, n in sorted(matches):
        noun = "block" if n == 1 else "blocks"
        if count:
            typer.echo(f"  {slug:52} {n} {noun}")
        else:
            typer.echo(f"  {slug}")
    typer.echo(f"\nTotal: {len(matches)} posts, {sum(n for _, n in matches)} blocks")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
