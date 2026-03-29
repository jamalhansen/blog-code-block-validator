from pathlib import Path
from typing import Optional
import typer
from typing import Annotated
from blog_validate.config import load_config
from blog_validate.extractor import scan_posts, build_fixture_registry, scan_helpers_dir
from blog_validate.languages.base import AnnotationType
from blog_validate.runner import (
    PostResult,
    get_changed_files,
    resolve_changed_posts,
    run_post,
)

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")


def _code_preview(code: str, max_lines: int = 3) -> str:
    lines = code.strip().splitlines()
    preview = "\n".join(f"    {line}" for line in lines[:max_lines])
    if len(lines) > max_lines:
        preview += "\n    ..."
    return preview


def _print_results(results: list[PostResult], verbose: bool) -> bool:
    """Print results. Returns True if any post failed."""
    any_failed = False
    for post_result in results:
        status = "PASS" if post_result.passed else "FAIL"
        counts = (
            f"passed={post_result.passed_count} "
            f"failed={post_result.failed_count} "
            f"skipped={post_result.skipped_count}"
        )
        typer.echo(f"[{status}] {post_result.slug}  ({counts})")
        if not post_result.passed or verbose:
            for r in post_result.results:
                if r.status == "failed":
                    typer.echo(
                        f"  FAIL block {r.block.block_index} ({r.block.language}): {r.error}"
                    )
                    typer.echo(_code_preview(r.block.code))
                elif verbose and r.status == "passed":
                    typer.echo(
                        f"  PASS block {r.block.block_index} ({r.block.language})"
                    )
        if not post_result.passed:
            any_failed = True
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
) -> None:
    """Validate code blocks in blog posts."""
    if not any([all_posts, changed, post]):
        typer.echo("Error: specify --all, --changed, or --post <slug>", err=True)
        raise typer.Exit(code=1)

    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root, config.blog.content_path, config.blog.post_file
    )
    base_blocks, helper_fixtures = scan_helpers_dir(config.root)
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


@app.command("list-fixtures")
def list_fixtures() -> None:
    """Show all named fixtures and the posts that define and use them."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(
        config.root, config.blog.content_path, config.blog.post_file
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
        config.root, config.blog.content_path, config.blog.post_file
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
        config.root, config.blog.content_path, config.blog.post_file
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


def main() -> None:
    app()


if __name__ == "__main__":
    main()
