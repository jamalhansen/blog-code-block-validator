from dataclasses import dataclass
from pathlib import Path
from typing import Callable
from blog_validate.extractor import FixtureRegistry, PostBlocks
from blog_validate.languages import VALIDATORS, make_context
from blog_validate.languages.base import AnnotationType, CodeBlock, ExecutionContext, ValidationError
from blog_validate.languages.sql import SQLValidator


@dataclass
class BlockResult:
    block: CodeBlock
    status: str  # "passed", "failed", "skipped"
    error: str | None = None


@dataclass
class PostResult:
    slug: str
    results: list[BlockResult]

    @property
    def passed(self) -> bool:
        return all(r.status != "failed" for r in self.results)

    @property
    def passed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "passed")

    @property
    def failed_count(self) -> int:
        return sum(1 for r in self.results if r.status == "failed")

    @property
    def skipped_count(self) -> int:
        return sum(1 for r in self.results if r.status == "skipped")


def _run_block(
    block: CodeBlock,
    ctx: ExecutionContext,
    fixture_registry: FixtureRegistry,
    dry_run: bool,
    verbose: bool,
    print_fn: Callable[[str], None] = print,
) -> BlockResult:
    if dry_run:
        return BlockResult(block=block, status="skipped", error="dry-run")

    if verbose:
        print_fn(f"  [{block.annotation.value}] {block.language} block {block.block_index}")

    annotation = block.annotation

    if annotation == AnnotationType.SKIP:
        return BlockResult(block=block, status="skipped")

    if annotation == AnnotationType.FIXTURE:
        # Fixture blocks are skipped in document flow; they execute when referenced via USE
        return BlockResult(block=block, status="skipped")

    if annotation == AnnotationType.USE:
        name = block.fixture_name
        if not name or name not in fixture_registry:
            return BlockResult(block=block, status="failed", error=f"Unknown fixture: {name!r}")
        fixture = fixture_registry[name]
        validator = VALIDATORS.get(fixture.language)
        if validator is None:
            return BlockResult(block=block, status="skipped",
                               error=f"No validator for fixture language {fixture.language!r}")
        try:
            validator.execute(fixture.code, ctx)
            return BlockResult(block=block, status="passed")
        except ValidationError as e:
            return BlockResult(block=block, status="failed", error=f"Fixture {name!r} failed: {e}")

    validator = VALIDATORS.get(block.language)
    if validator is None:
        return BlockResult(block=block, status="skipped",
                           error=f"No validator for language {block.language!r}")

    if annotation == AnnotationType.SYNTAX_ONLY:
        try:
            validator.syntax_check(block.code)
            return BlockResult(block=block, status="passed")
        except ValidationError as e:
            return BlockResult(block=block, status="failed", error=str(e))

    if annotation == AnnotationType.EXPECTED_FAILURE:
        try:
            validator.execute(block.code, ctx)
            return BlockResult(block=block, status="failed",
                               error="Expected failure but code succeeded")
        except ValidationError:
            return BlockResult(block=block, status="passed")

    if annotation == AnnotationType.ASSERT:
        if isinstance(validator, SQLValidator):
            try:
                validator.execute_assert(block.code, ctx)
                return BlockResult(block=block, status="passed")
            except ValidationError as e:
                return BlockResult(block=block, status="failed", error=str(e))
        else:
            try:
                validator.execute(block.code, ctx)
                return BlockResult(block=block, status="passed")
            except ValidationError as e:
                return BlockResult(block=block, status="failed", error=str(e))

    # DEFAULT and SETUP: execute, fail on any error
    try:
        validator.execute(block.code, ctx)
        return BlockResult(block=block, status="passed")
    except ValidationError as e:
        return BlockResult(block=block, status="failed", error=str(e))


def run_post(
    post: PostBlocks,
    fixture_registry: FixtureRegistry,
    helpers_path: Path | None = None,
    dry_run: bool = False,
    verbose: bool = False,
    print_fn: Callable[[str], None] = print,
) -> PostResult:
    ctx = make_context()

    if helpers_path and helpers_path.exists():
        helpers_code = helpers_path.read_text()
        exec(compile(helpers_code, str(helpers_path), "exec"), ctx.py_globals)

    results = [
        _run_block(b, ctx, fixture_registry, dry_run, verbose, print_fn)
        for b in post.blocks
    ]
    return PostResult(slug=post.slug, results=results)


def resolve_changed_posts(
    changed_files: list[Path],
    all_posts: list[PostBlocks],
    fixture_registry: FixtureRegistry,
    repo_root: Path,
    content_path: str,
    post_file: str,
) -> list[PostBlocks]:
    blog_root = repo_root / content_path

    # Map slug -> PostBlocks for quick lookup
    slug_map = {p.slug: p for p in all_posts}

    # Find directly changed post slugs
    changed_slugs: set[str] = set()
    for path in changed_files:
        try:
            rel = path.relative_to(blog_root)
        except ValueError:
            continue
        parts = rel.parts
        if len(parts) >= 2 and parts[-1] == post_file:
            changed_slugs.add(parts[0])

    if not changed_slugs:
        return []

    # Find fixture names defined in changed posts
    changed_fixture_names: set[str] = set()
    for slug in changed_slugs:
        if slug in slug_map:
            for block in slug_map[slug].blocks:
                if block.annotation == AnnotationType.FIXTURE and block.fixture_name:
                    changed_fixture_names.add(block.fixture_name)

    # Find consumer posts that USE any changed fixture
    consumer_slugs: set[str] = set()
    if changed_fixture_names:
        for post in all_posts:
            for block in post.blocks:
                if block.annotation == AnnotationType.USE and block.fixture_name in changed_fixture_names:
                    consumer_slugs.add(post.slug)

    all_affected = changed_slugs | consumer_slugs
    return [p for p in all_posts if p.slug in all_affected]


def get_changed_files() -> list[Path]:
    import subprocess
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        return []
    return [Path(line) for line in result.stdout.splitlines() if line]
