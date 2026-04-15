import re
from dataclasses import dataclass, field
from pathlib import Path
from blog_validate.languages.base import AnnotationType, CodeBlock

ANNOTATION_RE = re.compile(r'^<!-- test:([\w-]+)(?:\s+name="([^"]+)")?\s*-->$')
NEEDS_RE = re.compile(r"^<!-- test:needs:\s*([^>]+?)\s*-->$")
FixtureRegistry = dict[str, CodeBlock]

_LANG_BY_EXT: dict[str, str] = {".sql": "sql", ".py": "python"}


@dataclass
class PostBlocks:
    slug: str
    blocks: list[CodeBlock]
    needs: list[str] = field(default_factory=list)


def parse_annotation(line: str) -> tuple[AnnotationType, str | None] | None:
    """Parse a test annotation comment. Returns (type, fixture_name) or None."""
    m = ANNOTATION_RE.match(line.strip())
    if not m:
        return None

    tag = m.group(1)
    # Handle semantic markers like test:setup:start or test:assert:end
    # We strip the suffix to match the base AnnotationType
    if tag.endswith(":start") or tag.endswith(":end"):
        tag = tag.rsplit(":", 1)[0]

    try:
        annotation = AnnotationType(tag)
    except ValueError:
        return None
    return annotation, m.group(2)


def _parse_needs(content: str) -> list[str]:
    """Collect all <!-- test:needs: name1, name2 --> declarations in the file."""
    names: list[str] = []
    for line in content.split("\n"):
        m = NEEDS_RE.match(line.strip())
        if m:
            names.extend(n.strip() for n in m.group(1).split(",") if n.strip())
    return names


def extract_blocks(content: str, slug: str) -> list[CodeBlock]:
    """Extract all annotated code blocks from markdown content in document order."""
    lines = content.split("\n")
    blocks: list[CodeBlock] = []
    i = 0

    while i < len(lines):
        stripped = lines[i].strip()

        # Check for annotation comment
        result = parse_annotation(stripped)
        if result is not None:
            annotation, fixture_name = result
            i += 1
            # Consume blank lines between annotation and fence
            while i < len(lines) and not lines[i].strip():
                i += 1
            # If the next non-blank line is a code fence, consume with annotation
            if i < len(lines):
                fence_m = re.match(r"^```(\w+)\s*$", lines[i].strip())
                if fence_m:
                    i = _consume_fence(
                        lines,
                        i,
                        fence_m.group(1),
                        annotation,
                        fixture_name,
                        slug,
                        blocks,
                    )
                    continue
            # Annotation not followed by a fence — orphaned, skip
            continue

        # Check for bare code fence (no annotation)
        fence_m = re.match(r"^```(\w+)\s*$", stripped)
        if fence_m:
            i = _consume_fence(
                lines, i, fence_m.group(1), AnnotationType.DEFAULT, None, slug, blocks
            )
            continue

        i += 1

    return blocks


def _consume_fence(
    lines: list[str],
    i: int,
    lang: str,
    annotation: AnnotationType,
    fixture_name: str | None,
    slug: str,
    blocks: list[CodeBlock],
) -> int:
    """Consume a code fence starting at lines[i], append block, return new i."""
    i += 1  # skip opening ```lang
    fence_lines: list[str] = []
    while i < len(lines) and not re.match(r"^```\s*$", lines[i].strip()):
        fence_lines.append(lines[i])
        i += 1
    if i < len(lines):
        i += 1  # skip closing ```
    blocks.append(
        CodeBlock(
            language=lang,
            code="\n".join(fence_lines).strip(),
            annotation=annotation,
            fixture_name=fixture_name,
            post_slug=slug,
            block_index=len(blocks),
        )
    )
    return i


def scan_posts(
    blog_root: Path,
    content_path: str,
    post_file: str,
    layout: str = "bundle",
    exclude_patterns: list[str] | None = None,
) -> list[PostBlocks]:
    """Scan all posts and extract their code blocks."""
    posts_dir = blog_root / content_path
    if not posts_dir.exists():
        return []

    exclude_patterns = exclude_patterns or []
    results = []
    if layout == "flat":
        # Scan all .md files in the content directory
        for path in sorted(posts_dir.glob("*.md")):
            if any(path.match(p) for p in exclude_patterns):
                continue
            content = path.read_text()
            slug = path.stem
            blocks = extract_blocks(content, slug)
            needs = _parse_needs(content)
            results.append(PostBlocks(slug=slug, blocks=blocks, needs=needs))
    elif layout == "vault":
        # Vault layout: blog/series/[series]/posts/[slug]/[descriptive-name].md
        # We walk all subdirectories and for each leaf directory, take the first .md
        for post_dir in sorted(posts_dir.rglob("*")):
            if not post_dir.is_dir():
                continue

            # Check if this directory contains any .md files
            md_files = sorted(post_dir.glob("*.md"))
            if not md_files:
                continue

            # Filter out excluded patterns
            valid_mds = [
                f for f in md_files if not any(f.match(p) for p in exclude_patterns)
            ]
            if not valid_mds:
                continue

            # Take the first one as the post
            path = valid_mds[0]
            content = path.read_text()
            slug = post_dir.name
            blocks = extract_blocks(content, slug)
            needs = _parse_needs(content)
            results.append(PostBlocks(slug=slug, blocks=blocks, needs=needs))
    else:
        # Default bundle layout: each post is a directory with a specific post_file
        # We use rglob to find all instances of post_file (e.g. index.md) at any depth
        for path in sorted(posts_dir.rglob(post_file)):
            if any(path.match(p) for p in exclude_patterns):
                continue
            content = path.read_text()
            # Slug is the immediate parent directory name
            slug = path.parent.name
            blocks = extract_blocks(content, slug)
            needs = _parse_needs(content)
            results.append(PostBlocks(slug=slug, blocks=blocks, needs=needs))

    return results


def scan_helpers_dir(
    blog_root: Path,
) -> tuple[list[CodeBlock], FixtureRegistry]:
    """Scan blog-validate-helpers/ for named helper files.

    Returns:
        base_blocks: files whose names start with '_' — auto-run before every post
        named: all other files, registered by filename stem for opt-in via test:needs
    """
    helpers_dir = blog_root / "blog-validate-helpers"
    base_blocks: list[CodeBlock] = []
    named: FixtureRegistry = {}

    if not helpers_dir.exists():
        return base_blocks, named

    for path in sorted(helpers_dir.iterdir()):
        if path.suffix not in _LANG_BY_EXT:
            continue
        language = _LANG_BY_EXT[path.suffix]
        name = path.stem.lstrip("_")
        helper_block = CodeBlock(
            language=language,
            code=path.read_text(),
            annotation=AnnotationType.FIXTURE,
            fixture_name=name,
            post_slug="<helpers>",
            block_index=0,
        )
        if path.stem.startswith("_"):
            base_blocks.append(helper_block)
        else:
            named[name] = helper_block

    return base_blocks, named


def build_fixture_registry(all_posts: list[PostBlocks]) -> FixtureRegistry:
    """Build a registry of named fixtures from all posts."""
    registry: FixtureRegistry = {}
    for post in all_posts:
        for block in post.blocks:
            if block.annotation == AnnotationType.FIXTURE and block.fixture_name:
                registry[block.fixture_name] = block
    return registry
