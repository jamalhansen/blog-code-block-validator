from pathlib import Path
from typing import Optional
import typer
from typing import Annotated
from rich.console import Console
from rich.table import Table
from rich import box
from blog_validate.config import load_config
from blog_validate.env import setup_environment
from blog_validate.extractor import scan_posts, build_fixture_registry, scan_helpers_dir
from blog_validate.languages.base import AnnotationType
from blog_validate.runner import (
    PostResult,
    get_changed_files,
    resolve_changed_posts,
    run_post,
)
from blog_validate.inspector import analyze_post, format_guide, _has_assert_statements

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")


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
) -> None:
    """Validate code blocks in blog posts."""
    if not any([all_posts, changed, post]):
        typer.echo("Error: specify --all, --changed, or --post <slug>", err=True)
        raise typer.Exit(code=1)

    config = load_config(Path.cwd(), Path(config_path) if config_path else None)
    setup_environment(config.root, config.python.dependencies)

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

    if not posts_to_check:
        typer.echo("No posts to validate.")
        raise typer.Exit(code=0)

    results = [
        run_post(
            p,
            fixture_registry,
            base_blocks=base_blocks or None,
            dry_run=dry_run,
            verbose=verbose,
        )
        for p in posts_to_check
    ]

    any_failed = _print_results(results, verbose)
    passed = sum(1 for r in results if r.passed)
    typer.echo(f"\nDone. {passed}/{len(results)} posts passed.")

    if any_failed:
        raise typer.Exit(code=1)


@app.command("coverage")
def coverage(
    unannotated_only: Annotated[
        bool, typer.Option("--unannotated", help="List only posts with unannotated blocks")
    ] = False,
    show_all: Annotated[
        bool, typer.Option("--all", help="Include posts with no code blocks")
    ] = False,
) -> None:
    """Report annotation coverage across all posts."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

    _EXECUTED = {AnnotationType.DEFAULT, AnnotationType.SETUP, AnnotationType.ASSERT}

    no_blocks = 0
    fully_covered = 0
    needs_attention = 0

    unannotated_posts = []
    skip_counts: dict[str, int] = {}

    # assertion effectiveness tracking
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
            unannotated_posts.append((post.slug, unannotated_count))
        else:
            fully_covered += 1

        executed = [b for b in post.blocks if b.annotation in _EXECUTED]
        asserted = sum(
            1 for b in executed
            if b.annotation == AnnotationType.ASSERT or _has_assert_statements(b.code)
        )
        if executed:
            post_effectiveness.append((post.slug, asserted, len(executed)))

    typer.echo("Coverage report")
    typer.echo("─" * 47)
    if show_all or no_blocks == 0:
        typer.echo(f"Posts with no code blocks:          {no_blocks:2}  (skipped — nothing to annotate)")
    typer.echo(f"Posts with only annotated blocks:   {fully_covered:2}  (fully covered)")
    typer.echo(f"Posts with unannotated blocks:      {needs_attention:2}  (needs attention)")

    if unannotated_posts:
        typer.echo("\nUnannotated posts:")
        for slug, count in unannotated_posts:
            noun = "block" if count == 1 else "blocks"
            typer.echo(f"  {slug:50} {count} unannotated {noun}")

    if not unannotated_only and skip_counts:
        typer.echo("\nSkipped blocks by reason:")
        for reason, count in sorted(skip_counts.items()):
            typer.echo(f"  {reason:20} {count:2}")

    if not unannotated_only and post_effectiveness:
        total_asserted = sum(a for _, a, _ in post_effectiveness)
        total_executed = sum(e for _, _, e in post_effectiveness)
        pct = int(100 * total_asserted / total_executed) if total_executed else 0
        typer.echo(f"\nAssertion effectiveness: {total_asserted}/{total_executed} executed blocks assert output  ({pct}%)")
        unverified = [(s, e - a) for s, a, e in post_effectiveness if a < e]
        if unverified:
            typer.echo("Posts with unverified blocks:")
            for slug, gap in sorted(unverified, key=lambda x: -x[1]):
                noun = "block" if gap == 1 else "blocks"
                typer.echo(f"  {slug:50} {gap} unverified {noun}")


@app.command("list-fixtures")
def list_fixtures() -> None:
    """Show all named fixtures and the posts that define and use them."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )
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
def list_posts() -> None:
    """Show all posts with code blocks and their annotation counts."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

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
def list_skips() -> None:
    """Show all skipped blocks with a code preview."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

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
) -> None:
    """Show a testing checklist for a post without executing any code."""
    if not post and not all_posts:
        typer.echo("Error: specify --post <slug> or --all", err=True)
        raise typer.Exit(code=1)

    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

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
def stats() -> None:
    """Show block count by language across all posts."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

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
) -> None:
    """List posts that contain blocks of a given language."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root,
        config.blog.content_path,
        config.blog.post_file,
        config.blog.layout,
        config.blog.exclude_patterns,
    )

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
