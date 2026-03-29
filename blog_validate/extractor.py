import re
from dataclasses import dataclass
from pathlib import Path
from blog_validate.languages.base import AnnotationType, CodeBlock

ANNOTATION_RE = re.compile(r'^<!-- test:([\w-]+)(?:\s+name="([^"]+)")?\s*-->$')
FixtureRegistry = dict[str, CodeBlock]


@dataclass
class PostBlocks:
    slug: str
    blocks: list[CodeBlock]


def parse_annotation(line: str) -> tuple[AnnotationType, str | None] | None:
    """Parse a test annotation comment. Returns (type, fixture_name) or None."""
    m = ANNOTATION_RE.match(line.strip())
    if not m:
        return None
    try:
        annotation = AnnotationType(m.group(1))
    except ValueError:
        return None
    return annotation, m.group(2)


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


def scan_posts(blog_root: Path, content_path: str, post_file: str) -> list[PostBlocks]:
    """Scan all post directories and extract their code blocks."""
    posts_dir = blog_root / content_path
    if not posts_dir.exists():
        return []
    results = []
    for post_dir in sorted(posts_dir.iterdir()):
        if not post_dir.is_dir():
            continue
        index_file = post_dir / post_file
        if not index_file.exists():
            continue
        content = index_file.read_text()
        slug = post_dir.name
        blocks = extract_blocks(content, slug)
        results.append(PostBlocks(slug=slug, blocks=blocks))
    return results


def build_fixture_registry(all_posts: list[PostBlocks]) -> FixtureRegistry:
    """Build a registry of named fixtures from all posts."""
    registry: FixtureRegistry = {}
    for post in all_posts:
        for block in post.blocks:
            if block.annotation == AnnotationType.FIXTURE and block.fixture_name:
                registry[block.fixture_name] = block
    return registry
