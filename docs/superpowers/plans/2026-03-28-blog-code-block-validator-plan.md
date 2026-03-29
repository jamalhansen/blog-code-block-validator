# Blog Code Block Validator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a CLI tool that extracts annotated code blocks from Hugo blog posts and validates them, running as a pre-commit hook.

**Architecture:** Markdown posts are scanned for `<!-- test:* -->` HTML comment annotations immediately before code fences. A fixture registry collects named shared fixtures from all posts at startup. The runner processes each post's blocks in document order, delegating to language-specific validators, then reports results.

**Tech Stack:** Python 3.11+, Typer (CLI), DuckDB (SQL execution), pytest (tests), uv (package manager), tomllib (stdlib, Python 3.11+)

---

## File Map

| File | Responsibility |
|---|---|
| `pyproject.toml` | Package metadata, deps, CLI entry point |
| `blog_validate/__init__.py` | Package marker |
| `blog_validate/config.py` | Load `blog-validate.toml`, walk up directories |
| `blog_validate/languages/base.py` | `AnnotationType`, `CodeBlock`, `ExecutionContext`, `ValidationError`, `Validator` ABC |
| `blog_validate/languages/python.py` | Python syntax check + exec |
| `blog_validate/languages/sql.py` | SQL syntax check + execute + execute_assert |
| `blog_validate/languages/__init__.py` | `VALIDATORS` dict, `make_context()` |
| `blog_validate/extractor.py` | `parse_annotation`, `extract_blocks`, `scan_posts`, `build_fixture_registry` |
| `blog_validate/runner.py` | `run_post`, `resolve_changed_posts`, `get_changed_files`, `PostResult`, `BlockResult` |
| `blog_validate/main.py` | Typer app: `check`, `list-fixtures`, `list-posts` |
| `scripts/hooks/pre-commit` | Canonical pre-commit hook for blog repo |
| `tests/test_config.py` | Config loader tests |
| `tests/test_base.py` | Base type tests |
| `tests/test_extractor.py` | Annotation parsing + block extraction tests |
| `tests/test_python_validator.py` | Python validator tests |
| `tests/test_sql_validator.py` | SQL validator tests |
| `tests/test_runner.py` | Runner orchestration tests |
| `tests/test_main.py` | CLI integration tests |

---

## Task 1: Project Scaffolding

**Files:**
- Create: `pyproject.toml`
- Create: `blog_validate/__init__.py`
- Create: `blog_validate/main.py` (stub)
- Create: `blog_validate/languages/__init__.py` (empty)
- Create: `tests/__init__.py`

- [ ] **Step 1: Initialize project with uv**

```bash
cd ~/projects/blog-code-block-validator
uv init --name blog-code-block-validator
uv add typer duckdb python-frontmatter
uv add --dev pytest
```

- [ ] **Step 2: Configure pyproject.toml**

Replace the generated `pyproject.toml` with:

```toml
[project]
name = "blog-code-block-validator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = [
    "typer>=0.12",
    "duckdb>=0.10",
]

[project.scripts]
blog-validate = "blog_validate.main:app"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["blog_validate"]

[dependency-groups]
dev = [
    "pytest>=8.0",
]
```

- [ ] **Step 3: Create package structure**

```bash
mkdir -p blog_validate/languages
touch blog_validate/__init__.py
touch blog_validate/languages/__init__.py
touch tests/__init__.py
```

- [ ] **Step 4: Create main.py stub**

```python
# blog_validate/main.py
import typer

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Verify install works**

```bash
uv run blog-validate --help
```

Expected output: `Usage: blog-validate [OPTIONS] COMMAND [ARGS]...`

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml blog_validate/ tests/__init__.py
git commit -m "feat: scaffold project structure"
```

---

## Task 2: Config Loader

**Files:**
- Create: `blog_validate/config.py`
- Create: `tests/test_config.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_config.py
import pytest
from pathlib import Path
from blog_validate.config import load_config


def test_load_config_finds_toml_in_current_dir(tmp_path):
    (tmp_path / "blog-validate.toml").write_text(
        '[blog]\ncontent_path = "content/posts"\n'
    )
    config = load_config(tmp_path)
    assert config.blog.content_path == "content/posts"
    assert config.root == tmp_path


def test_load_config_walks_up_to_parent(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    subdir = tmp_path / "content" / "blog" / "my-post"
    subdir.mkdir(parents=True)
    config = load_config(subdir)
    assert config.root == tmp_path


def test_load_config_uses_defaults_for_missing_keys(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    config = load_config(tmp_path)
    assert config.blog.content_path == "content/blog"
    assert config.blog.post_file == "index.md"
    assert config.sql.backend == "duckdb"


def test_load_config_raises_if_not_found(tmp_path):
    isolated = tmp_path / "deep" / "nested"
    isolated.mkdir(parents=True)
    # Patch filesystem root check — stop walking at tmp_path
    with pytest.raises(FileNotFoundError, match="blog-validate.toml not found"):
        # This works as long as no parent dir of tmp_path has a blog-validate.toml
        # (true in all CI and local environments)
        load_config(isolated)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_config.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.config'`

- [ ] **Step 3: Implement config.py**

```python
# blog_validate/config.py
from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass
class BlogConfig:
    content_path: str = "content/blog"
    post_file: str = "index.md"


@dataclass
class SqlConfig:
    backend: str = "duckdb"


@dataclass
class Config:
    blog: BlogConfig
    sql: SqlConfig
    root: Path


def load_config(start_dir: Path) -> Config:
    """Walk up from start_dir to find blog-validate.toml."""
    current = start_dir.resolve()
    while True:
        toml_path = current / "blog-validate.toml"
        if toml_path.exists():
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            blog_data = data.get("blog", {})
            sql_data = data.get("sql", {})
            return Config(
                blog=BlogConfig(**blog_data),
                sql=SqlConfig(**sql_data),
                root=current,
            )
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "blog-validate.toml not found in any parent directory"
            )
        current = parent
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_config.py -v
```

Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/config.py tests/test_config.py
git commit -m "feat: add config loader with upward directory walk"
```

---

## Task 3: Base Types

**Files:**
- Create: `blog_validate/languages/base.py`
- Create: `tests/test_base.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_base.py
import pytest
import duckdb
from blog_validate.languages.base import (
    AnnotationType, CodeBlock, ExecutionContext, ValidationError, Validator,
)


def test_annotation_type_string_values():
    assert AnnotationType.DEFAULT == "default"
    assert AnnotationType.SKIP == "skip"
    assert AnnotationType.EXPECTED_FAILURE == "expected-failure"
    assert AnnotationType.SYNTAX_ONLY == "syntax-only"
    assert AnnotationType.ASSERT == "assert"
    assert AnnotationType.FIXTURE == "fixture"
    assert AnnotationType.USE == "use"


def test_code_block_has_defaults():
    block = CodeBlock(language="python", code="x = 1", annotation=AnnotationType.DEFAULT)
    assert block.fixture_name is None
    assert block.post_slug == ""
    assert block.block_index == 0


def test_execution_context_has_empty_globals_by_default():
    conn = duckdb.connect(":memory:")
    ctx = ExecutionContext(conn=conn)
    assert ctx.py_globals == {}


def test_validation_error_is_exception():
    err = ValidationError("bad code")
    assert isinstance(err, Exception)
    assert str(err) == "bad code"


def test_validator_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Validator()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_base.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.languages.base'`

- [ ] **Step 3: Implement base.py**

```python
# blog_validate/languages/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnnotationType(str, Enum):
    DEFAULT = "default"
    SKIP = "skip"
    EXPECTED_FAILURE = "expected-failure"
    SETUP = "setup"
    SYNTAX_ONLY = "syntax-only"
    ASSERT = "assert"
    FIXTURE = "fixture"
    USE = "use"


@dataclass
class CodeBlock:
    language: str
    code: str
    annotation: AnnotationType
    fixture_name: str | None = None
    post_slug: str = ""
    block_index: int = 0


@dataclass
class ExecutionContext:
    conn: Any  # duckdb.DuckDBPyConnection
    py_globals: dict = field(default_factory=dict)


class ValidationError(Exception):
    pass


class Validator(ABC):
    language: str

    @abstractmethod
    def syntax_check(self, code: str) -> None:
        """Check syntax only. Raise ValidationError if invalid."""

    @abstractmethod
    def execute(self, code: str, context: ExecutionContext) -> None:
        """Execute code in context. Raise ValidationError on failure."""
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_base.py -v
```

Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/languages/base.py tests/test_base.py
git commit -m "feat: add base types — AnnotationType, CodeBlock, ExecutionContext, Validator"
```

---

## Task 4: Extractor — Annotation Parsing and Block Extraction

**Files:**
- Create: `blog_validate/extractor.py`
- Create: `tests/test_extractor.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_extractor.py
import pytest
from blog_validate.extractor import parse_annotation, extract_blocks
from blog_validate.languages.base import AnnotationType


class TestParseAnnotation:
    def test_parses_skip(self):
        assert parse_annotation("<!-- test:skip -->") == (AnnotationType.SKIP, None)

    def test_parses_expected_failure(self):
        assert parse_annotation("<!-- test:expected-failure -->") == (AnnotationType.EXPECTED_FAILURE, None)

    def test_parses_setup(self):
        assert parse_annotation("<!-- test:setup -->") == (AnnotationType.SETUP, None)

    def test_parses_syntax_only(self):
        assert parse_annotation("<!-- test:syntax-only -->") == (AnnotationType.SYNTAX_ONLY, None)

    def test_parses_assert(self):
        assert parse_annotation("<!-- test:assert -->") == (AnnotationType.ASSERT, None)

    def test_parses_fixture_with_name(self):
        assert parse_annotation('<!-- test:fixture name="my-table" -->') == (AnnotationType.FIXTURE, "my-table")

    def test_parses_use_with_name(self):
        assert parse_annotation('<!-- test:use name="my-table" -->') == (AnnotationType.USE, "my-table")

    def test_returns_none_for_plain_text(self):
        assert parse_annotation("Some text") is None

    def test_returns_none_for_code_fence(self):
        assert parse_annotation("```python") is None

    def test_returns_none_for_empty_string(self):
        assert parse_annotation("") is None

    def test_returns_none_for_unknown_type(self):
        assert parse_annotation("<!-- test:unknown -->") is None


class TestExtractBlocks:
    def test_extracts_bare_code_block_as_default(self):
        blocks = extract_blocks("```python\nx = 1\n```", "my-post")
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].code == "x = 1"
        assert blocks[0].annotation == AnnotationType.DEFAULT

    def test_extracts_annotated_block(self):
        content = "<!-- test:skip -->\n```python\nimport missing\n```"
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 1
        assert blocks[0].annotation == AnnotationType.SKIP

    def test_extracts_fixture_block_with_name(self):
        content = '<!-- test:fixture name="users-table" -->\n```sql\nCREATE TABLE users (id INT);\n```'
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].annotation == AnnotationType.FIXTURE
        assert blocks[0].fixture_name == "users-table"

    def test_multiple_blocks_in_document_order(self):
        content = (
            "```python\nx = 1\n```\n\n"
            "<!-- test:skip -->\n```sql\nSELECT 1\n```\n\n"
            "```python\ny = 2\n```"
        )
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 3
        assert blocks[0].annotation == AnnotationType.DEFAULT
        assert blocks[1].annotation == AnnotationType.SKIP
        assert blocks[2].annotation == AnnotationType.DEFAULT

    def test_block_indices_increment(self):
        content = "```python\nx = 1\n```\n```python\ny = 2\n```"
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].block_index == 0
        assert blocks[1].block_index == 1

    def test_post_slug_set_on_blocks(self):
        blocks = extract_blocks("```python\nx = 1\n```", "my-slug")
        assert blocks[0].post_slug == "my-slug"

    def test_orphaned_annotation_not_applied(self):
        # Annotation followed by non-fence text is orphaned; bare fence gets DEFAULT
        content = "<!-- test:skip -->\nSome text here\n```python\nx = 1\n```"
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 1
        assert blocks[0].annotation == AnnotationType.DEFAULT

    def test_blank_lines_between_annotation_and_fence_ok(self):
        content = "<!-- test:skip -->\n\n```python\nx = 1\n```"
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].annotation == AnnotationType.SKIP

    def test_returns_empty_for_no_code_blocks(self):
        blocks = extract_blocks("Just some text\nNo code here", "my-post")
        assert blocks == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_extractor.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.extractor'`

- [ ] **Step 3: Implement extractor.py (parse_annotation + extract_blocks)**

```python
# blog_validate/extractor.py
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
                    i = _consume_fence(lines, i, fence_m.group(1), annotation, fixture_name, slug, blocks)
                    continue
            # Annotation not followed by a fence — orphaned, skip
            continue

        # Check for bare code fence (no annotation)
        fence_m = re.match(r"^```(\w+)\s*$", stripped)
        if fence_m:
            i = _consume_fence(lines, i, fence_m.group(1), AnnotationType.DEFAULT, None, slug, blocks)
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
    blocks.append(CodeBlock(
        language=lang,
        code="\n".join(fence_lines).strip(),
        annotation=annotation,
        fixture_name=fixture_name,
        post_slug=slug,
        block_index=len(blocks),
    ))
    return i
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_extractor.py -v
```

Expected: 20 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/extractor.py tests/test_extractor.py
git commit -m "feat: add extractor — annotation parsing and block extraction"
```

---

## Task 5: Extractor — Post Scanning and Fixture Registry

**Files:**
- Modify: `blog_validate/extractor.py`
- Modify: `tests/test_extractor.py`

- [ ] **Step 1: Write the failing tests** (add to `tests/test_extractor.py`)

```python
from blog_validate.extractor import scan_posts, build_fixture_registry, PostBlocks
from blog_validate.languages.base import AnnotationType, CodeBlock


class TestScanPosts:
    def test_scans_posts_from_content_dir(self, tmp_path):
        post_dir = tmp_path / "content" / "blog" / "my-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```python\nx = 1\n```")

        posts = scan_posts(tmp_path, "content/blog", "index.md")

        assert len(posts) == 1
        assert posts[0].slug == "my-post"
        assert len(posts[0].blocks) == 1

    def test_ignores_files_not_directories(self, tmp_path):
        posts_dir = tmp_path / "content" / "blog"
        posts_dir.mkdir(parents=True)
        (posts_dir / "_index.md").write_text("---\n---\n")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert posts == []

    def test_returns_empty_for_missing_content_path(self, tmp_path):
        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert posts == []

    def test_posts_sorted_by_slug(self, tmp_path):
        for slug in ["zzz-post", "aaa-post", "mmm-post"]:
            d = tmp_path / "content" / "blog" / slug
            d.mkdir(parents=True)
            (d / "index.md").write_text("```python\nx = 1\n```")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        slugs = [p.slug for p in posts]
        assert slugs == sorted(slugs)

    def test_post_with_no_code_blocks_still_included(self, tmp_path):
        post_dir = tmp_path / "content" / "blog" / "prose-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("Just text, no code.")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert len(posts) == 1
        assert posts[0].blocks == []


class TestBuildFixtureRegistry:
    def test_registers_fixture_blocks(self):
        block = CodeBlock(
            language="sql", code="CREATE TABLE t (id INT);",
            annotation=AnnotationType.FIXTURE, fixture_name="my-table",
            post_slug="post-1", block_index=0,
        )
        registry = build_fixture_registry([PostBlocks(slug="post-1", blocks=[block])])
        assert "my-table" in registry
        assert registry["my-table"].code == "CREATE TABLE t (id INT);"

    def test_ignores_non_fixture_blocks(self):
        block = CodeBlock(
            language="sql", code="SELECT 1",
            annotation=AnnotationType.DEFAULT,
            post_slug="post-1", block_index=0,
        )
        registry = build_fixture_registry([PostBlocks(slug="post-1", blocks=[block])])
        assert len(registry) == 0

    def test_collects_fixtures_across_multiple_posts(self):
        posts = [
            PostBlocks(slug="post-1", blocks=[
                CodeBlock(language="sql", code="CREATE TABLE a (id INT);",
                         annotation=AnnotationType.FIXTURE, fixture_name="table-a",
                         post_slug="post-1", block_index=0)
            ]),
            PostBlocks(slug="post-2", blocks=[
                CodeBlock(language="sql", code="CREATE TABLE b (id INT);",
                         annotation=AnnotationType.FIXTURE, fixture_name="table-b",
                         post_slug="post-2", block_index=0)
            ]),
        ]
        registry = build_fixture_registry(posts)
        assert "table-a" in registry
        assert "table-b" in registry
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_extractor.py::TestScanPosts tests/test_extractor.py::TestBuildFixtureRegistry -v
```

Expected: `ImportError` for `scan_posts`, `build_fixture_registry`

- [ ] **Step 3: Implement scan_posts and build_fixture_registry** (add to `blog_validate/extractor.py`)

```python
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
```

- [ ] **Step 4: Run all extractor tests**

```bash
uv run pytest tests/test_extractor.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/extractor.py tests/test_extractor.py
git commit -m "feat: add scan_posts and build_fixture_registry"
```

---

## Task 6: Python Validator

**Files:**
- Create: `blog_validate/languages/python.py`
- Create: `tests/test_python_validator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_python_validator.py
import duckdb
import pytest
from blog_validate.languages.base import ExecutionContext, ValidationError
from blog_validate.languages.python import PythonValidator


@pytest.fixture
def ctx():
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={"conn": conn})


@pytest.fixture
def validator():
    return PythonValidator()


class TestPythonSyntaxCheck:
    def test_valid_syntax_passes(self, validator):
        validator.syntax_check("x = 1 + 2")

    def test_syntax_error_raises_validation_error(self, validator):
        with pytest.raises(ValidationError, match="Python syntax error"):
            validator.syntax_check("def foo(:\n    pass")

    def test_undefined_variable_is_valid_syntax(self, validator):
        # syntax_check should not catch runtime errors
        validator.syntax_check("x = undefined_variable + 1")


class TestPythonExecute:
    def test_simple_assignment_executes(self, validator, ctx):
        validator.execute("x = 1 + 2", ctx)
        assert ctx.py_globals["x"] == 3

    def test_passing_assert_does_not_raise(self, validator, ctx):
        validator.execute("assert 1 == 1", ctx)

    def test_failing_assert_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="Assertion failed"):
            validator.execute("assert 1 == 2, 'not equal'", ctx)

    def test_runtime_exception_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="Python execution error"):
            validator.execute("raise RuntimeError('boom')", ctx)

    def test_globals_persist_across_calls(self, validator, ctx):
        validator.execute("x = 42", ctx)
        validator.execute("y = x + 1", ctx)
        assert ctx.py_globals["y"] == 43

    def test_conn_is_available_in_globals(self, validator, ctx):
        validator.execute("result = conn.execute('SELECT 42').fetchone()[0]", ctx)
        assert ctx.py_globals["result"] == 42
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_python_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.languages.python'`

- [ ] **Step 3: Implement python.py**

```python
# blog_validate/languages/python.py
import ast
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class PythonValidator(Validator):
    language = "python"

    def syntax_check(self, code: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValidationError(f"Python syntax error: {e}") from e

    def execute(self, code: str, context: ExecutionContext) -> None:
        try:
            exec(compile(code, "<blog>", "exec"), context.py_globals)
        except AssertionError as e:
            raise ValidationError(f"Assertion failed: {e}") from e
        except Exception as e:
            raise ValidationError(f"Python execution error: {type(e).__name__}: {e}") from e
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_python_validator.py -v
```

Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/languages/python.py tests/test_python_validator.py
git commit -m "feat: add Python validator"
```

---

## Task 7: SQL Validator

**Files:**
- Create: `blog_validate/languages/sql.py`
- Create: `tests/test_sql_validator.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_sql_validator.py
import duckdb
import pytest
from blog_validate.languages.base import ExecutionContext, ValidationError
from blog_validate.languages.sql import SQLValidator


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def ctx(conn):
    return ExecutionContext(conn=conn, py_globals={})


@pytest.fixture
def validator():
    return SQLValidator()


class TestSQLSyntaxCheck:
    def test_valid_select_passes(self, validator):
        validator.syntax_check("SELECT 1")

    def test_syntax_error_raises_validation_error(self, validator):
        with pytest.raises(ValidationError, match="SQL syntax error"):
            validator.syntax_check("SELECT FROM WHERE")

    def test_missing_table_is_not_a_syntax_error(self, validator):
        # Semantic errors should not raise ValidationError in syntax_check
        validator.syntax_check("SELECT * FROM nonexistent_table")


class TestSQLExecute:
    def test_select_executes(self, validator, ctx):
        validator.execute("SELECT 42", ctx)

    def test_create_table_executes(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT)", ctx)

    def test_schema_persists_across_calls(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT)", ctx)
        validator.execute("INSERT INTO t VALUES (1)", ctx)
        validator.execute("SELECT * FROM t", ctx)

    def test_error_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL execution error"):
            validator.execute("SELECT * FROM nonexistent_table", ctx)


class TestSQLExecuteAssert:
    def test_truthy_result_passes(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT); INSERT INTO t VALUES (1),(2)", ctx)
        validator.execute_assert("SELECT COUNT(*) = 2 FROM t", ctx)

    def test_false_result_raises(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT); INSERT INTO t VALUES (1)", ctx)
        with pytest.raises(ValidationError, match="SQL assertion failed"):
            validator.execute_assert("SELECT COUNT(*) = 99 FROM t", ctx)

    def test_no_rows_raises(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL assertion returned no rows"):
            validator.execute_assert("SELECT 1 WHERE 1=0", ctx)

    def test_error_in_assert_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL assertion error"):
            validator.execute_assert("SELECT * FROM nonexistent", ctx)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_sql_validator.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.languages.sql'`

- [ ] **Step 3: Implement sql.py**

```python
# blog_validate/languages/sql.py
import duckdb
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class SQLValidator(Validator):
    language = "sql"

    def syntax_check(self, code: str) -> None:
        """Check SQL syntax using EXPLAIN against a fresh connection.

        Only raises ValidationError for Parser Errors. Semantic errors
        (missing tables, wrong types) are not syntax errors and are ignored.
        """
        try:
            conn = duckdb.connect(":memory:")
            conn.execute(f"EXPLAIN {code}")
            conn.close()
        except duckdb.Error as e:
            err = str(e)
            if "Parser Error" in err or "parser error" in err.lower():
                raise ValidationError(f"SQL syntax error: {e}") from e
            # Other errors (missing tables, etc.) are semantic, not syntax

    def execute(self, code: str, context: ExecutionContext) -> None:
        try:
            context.conn.execute(code)
        except Exception as e:
            raise ValidationError(f"SQL execution error: {type(e).__name__}: {e}") from e

    def execute_assert(self, code: str, context: ExecutionContext) -> None:
        """Execute as assertion. Query must return a single truthy value."""
        try:
            result = context.conn.execute(code).fetchone()
        except Exception as e:
            raise ValidationError(f"SQL assertion error: {type(e).__name__}: {e}") from e

        if result is None:
            raise ValidationError("SQL assertion returned no rows")

        if not result[0]:
            raise ValidationError(
                f"SQL assertion failed: expected truthy, got {result[0]!r}"
            )
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_sql_validator.py -v
```

Expected: 11 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/languages/sql.py tests/test_sql_validator.py
git commit -m "feat: add SQL validator with execute_assert support"
```

---

## Task 8: Languages __init__ (VALIDATORS + make_context)

**Files:**
- Modify: `blog_validate/languages/__init__.py`

- [ ] **Step 1: Implement languages/__init__.py**

```python
# blog_validate/languages/__init__.py
import duckdb
from blog_validate.languages.base import ExecutionContext, Validator
from blog_validate.languages.python import PythonValidator
from blog_validate.languages.sql import SQLValidator

VALIDATORS: dict[str, Validator] = {
    "python": PythonValidator(),
    "sql": SQLValidator(),
}


def make_context() -> ExecutionContext:
    """Create a fresh execution context for a post."""
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={"conn": conn})
```

- [ ] **Step 2: Verify existing tests still pass**

```bash
uv run pytest tests/ -v
```

Expected: all previously passing tests still pass

- [ ] **Step 3: Commit**

```bash
git add blog_validate/languages/__init__.py
git commit -m "feat: wire VALIDATORS dict and make_context"
```

---

## Task 9: Runner — Execute a Single Post

**Files:**
- Create: `blog_validate/runner.py`
- Create: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_runner.py
import pytest
from pathlib import Path
from blog_validate.extractor import PostBlocks
from blog_validate.languages.base import AnnotationType, CodeBlock
from blog_validate.runner import run_post


def block(language, code, annotation=AnnotationType.DEFAULT, fixture_name=None, index=0):
    return CodeBlock(
        language=language, code=code, annotation=annotation,
        fixture_name=fixture_name, post_slug="test-post", block_index=index,
    )


class TestRunPost:
    def test_default_sql_block_passes(self):
        post = PostBlocks(slug="test", blocks=[block("sql", "SELECT 1")])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "passed"

    def test_skip_block_is_skipped(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "import missing_module", AnnotationType.SKIP)
        ])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "skipped"

    def test_expected_failure_that_errors_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("sql", "SELECT * FROM nonexistent", AnnotationType.EXPECTED_FAILURE)
        ])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "passed"

    def test_expected_failure_that_succeeds_fails_test(self):
        post = PostBlocks(slug="test", blocks=[
            block("sql", "SELECT 1", AnnotationType.EXPECTED_FAILURE)
        ])
        result = run_post(post, {})
        assert not result.passed
        assert result.results[0].status == "failed"

    def test_syntax_only_valid_python_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "x = undefined_var", AnnotationType.SYNTAX_ONLY)
        ])
        result = run_post(post, {})
        assert result.passed

    def test_assert_sql_truthy_passes(self):
        setup_block = block("sql", "CREATE TABLE t (id INT); INSERT INTO t VALUES (1),(2)",
                           AnnotationType.SETUP, index=0)
        assert_block = block("sql", "SELECT COUNT(*) = 2 FROM t", AnnotationType.ASSERT, index=1)
        result = run_post(PostBlocks(slug="test", blocks=[setup_block, assert_block]), {})
        assert result.passed

    def test_assert_sql_false_fails_test(self):
        setup_block = block("sql", "CREATE TABLE t (id INT); INSERT INTO t VALUES (1)",
                           AnnotationType.SETUP, index=0)
        assert_block = block("sql", "SELECT COUNT(*) = 99 FROM t", AnnotationType.ASSERT, index=1)
        result = run_post(PostBlocks(slug="test", blocks=[setup_block, assert_block]), {})
        assert not result.passed

    def test_assert_python_passing_assert_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "assert 1 == 1", AnnotationType.ASSERT)
        ])
        result = run_post(post, {})
        assert result.passed

    def test_use_injects_fixture_before_block(self):
        fixture_block = block("sql", "CREATE TABLE users (id INT); INSERT INTO users VALUES (1)",
                             AnnotationType.FIXTURE, fixture_name="users-table")
        registry = {"users-table": fixture_block}
        use_block = block("sql", "", AnnotationType.USE, fixture_name="users-table", index=0)
        query_block = block("sql", "SELECT COUNT(*) FROM users", index=1)
        result = run_post(PostBlocks(slug="test", blocks=[use_block, query_block]), registry)
        assert result.passed

    def test_unknown_fixture_fails(self):
        use_block = block("sql", "", AnnotationType.USE, fixture_name="nonexistent", index=0)
        result = run_post(PostBlocks(slug="test", blocks=[use_block]), {})
        assert not result.passed
        assert "Unknown fixture" in result.results[0].error

    def test_dry_run_skips_all_execution(self):
        post = PostBlocks(slug="test", blocks=[block("sql", "SELECT 1")])
        result = run_post(post, {}, dry_run=True)
        assert all(r.status == "skipped" for r in result.results)

    def test_unknown_language_is_skipped(self):
        post = PostBlocks(slug="test", blocks=[block("bash", "echo hello")])
        result = run_post(post, {})
        assert result.results[0].status == "skipped"

    def test_fixture_block_in_document_is_skipped(self):
        # FIXTURE blocks in document flow are skipped (they run when referenced via USE)
        fixture = block("sql", "CREATE TABLE t (id INT);", AnnotationType.FIXTURE,
                       fixture_name="my-table")
        result = run_post(PostBlocks(slug="test", blocks=[fixture]), {})
        assert result.results[0].status == "skipped"

    def test_helpers_file_injected_into_python_context(self, tmp_path):
        helpers = tmp_path / "blog-validate-helpers.py"
        helpers.write_text("def greet(): return 'hello'")
        post = PostBlocks(slug="test", blocks=[
            block("python", "assert greet() == 'hello'", AnnotationType.ASSERT)
        ])
        result = run_post(post, {}, helpers_path=helpers)
        assert result.passed

    def test_post_result_counts(self):
        blocks = [
            block("sql", "SELECT 1", index=0),
            block("sql", "SELECT 1", AnnotationType.SKIP, index=1),
            block("sql", "SELECT * FROM nonexistent", index=2),
        ]
        result = run_post(PostBlocks(slug="test", blocks=blocks), {})
        assert result.passed_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert not result.passed
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_runner.py -v
```

Expected: `ModuleNotFoundError: No module named 'blog_validate.runner'`

- [ ] **Step 3: Implement runner.py**

```python
# blog_validate/runner.py
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_runner.py -v
```

Expected: 15 passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/runner.py tests/test_runner.py
git commit -m "feat: add runner — executes posts in document order, all annotation types"
```

---

## Task 10: Runner — Changed Post Resolution

**Files:**
- Modify: `blog_validate/runner.py`
- Modify: `tests/test_runner.py`

- [ ] **Step 1: Write the failing tests** (add to `tests/test_runner.py`)

```python
from blog_validate.runner import resolve_changed_posts, get_changed_files


class TestResolveChangedPosts:
    def test_includes_directly_changed_post(self, tmp_path):
        (tmp_path / "content" / "blog" / "my-post").mkdir(parents=True)
        post = PostBlocks(slug="my-post", blocks=[])
        changed = [tmp_path / "content" / "blog" / "my-post" / "index.md"]

        result = resolve_changed_posts(changed, [post], {}, tmp_path, "content/blog", "index.md")

        assert len(result) == 1
        assert result[0].slug == "my-post"

    def test_includes_posts_that_use_a_changed_fixture(self, tmp_path):
        posts_dir = tmp_path / "content" / "blog"
        (posts_dir / "fixture-post").mkdir(parents=True)
        (posts_dir / "consumer-post").mkdir(parents=True)

        fixture_block = CodeBlock(
            language="sql", code="CREATE TABLE t (id INT);",
            annotation=AnnotationType.FIXTURE, fixture_name="my-table",
            post_slug="fixture-post", block_index=0,
        )
        use_block = CodeBlock(
            language="sql", code="",
            annotation=AnnotationType.USE, fixture_name="my-table",
            post_slug="consumer-post", block_index=0,
        )
        fixture_post = PostBlocks(slug="fixture-post", blocks=[fixture_block])
        consumer_post = PostBlocks(slug="consumer-post", blocks=[use_block])

        changed = [tmp_path / "content" / "blog" / "fixture-post" / "index.md"]
        result = resolve_changed_posts(
            changed, [fixture_post, consumer_post], {"my-table": fixture_block},
            tmp_path, "content/blog", "index.md",
        )

        slugs = {p.slug for p in result}
        assert "fixture-post" in slugs
        assert "consumer-post" in slugs

    def test_ignores_files_outside_content_path(self, tmp_path):
        post = PostBlocks(slug="my-post", blocks=[])
        changed = [tmp_path / "README.md"]

        result = resolve_changed_posts(changed, [post], {}, tmp_path, "content/blog", "index.md")

        assert result == []

    def test_returns_empty_for_no_changed_files(self, tmp_path):
        post = PostBlocks(slug="my-post", blocks=[])
        result = resolve_changed_posts([], [post], {}, tmp_path, "content/blog", "index.md")
        assert result == []
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_runner.py::TestResolveChangedPosts -v
```

Expected: `ImportError` for `resolve_changed_posts`

- [ ] **Step 3: Implement resolve_changed_posts and get_changed_files** (add to `blog_validate/runner.py`)

```python
import subprocess


def resolve_changed_posts(
    changed_files: list[Path],
    all_posts: list[PostBlocks],
    fixture_registry: FixtureRegistry,
    blog_root: Path,
    content_path: str,
    post_file: str,
) -> list[PostBlocks]:
    """Return posts to validate: changed posts + posts that use their fixtures."""
    posts_dir = blog_root / content_path
    post_by_slug = {p.slug: p for p in all_posts}
    changed_slugs: set[str] = set()

    for f in changed_files:
        try:
            relative = f.relative_to(posts_dir)
            slug = relative.parts[0]
            if slug in post_by_slug:
                changed_slugs.add(slug)
        except ValueError:
            pass

    # Find fixtures defined in changed posts
    changed_fixture_names: set[str] = set()
    for slug in changed_slugs:
        for b in post_by_slug[slug].blocks:
            if b.annotation == AnnotationType.FIXTURE and b.fixture_name:
                changed_fixture_names.add(b.fixture_name)

    # Add posts that use any of those fixtures
    if changed_fixture_names:
        for post in all_posts:
            for b in post.blocks:
                if b.annotation == AnnotationType.USE and b.fixture_name in changed_fixture_names:
                    changed_slugs.add(post.slug)

    return [post_by_slug[s] for s in sorted(changed_slugs) if s in post_by_slug]


def get_changed_files(blog_root: Path) -> list[Path]:
    """Get staged files from git diff --cached."""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        capture_output=True, text=True, cwd=blog_root,
    )
    if result.returncode != 0:
        return []
    return [
        blog_root / line.strip()
        for line in result.stdout.strip().splitlines()
        if line.strip()
    ]
```

- [ ] **Step 4: Run all runner tests**

```bash
uv run pytest tests/test_runner.py -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/runner.py tests/test_runner.py
git commit -m "feat: add resolve_changed_posts and get_changed_files"
```

---

## Task 11: CLI — check Command

**Files:**
- Modify: `blog_validate/main.py`
- Create: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_main.py
import pytest
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()


@pytest.fixture
def blog_root(tmp_path):
    (tmp_path / "blog-validate.toml").write_text(
        '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
    )
    post_dir = tmp_path / "content" / "blog" / "my-post"
    post_dir.mkdir(parents=True)
    (post_dir / "index.md").write_text("# My Post\n\n```sql\nSELECT 1\n```\n")
    return tmp_path


class TestCheckCommand:
    def test_check_all_passes_valid_blog(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_post_by_slug_passes(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--post", "my-post"])
        assert result.exit_code == 0

    def test_check_unknown_slug_exits_1(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--post", "nonexistent"])
        assert result.exit_code == 1

    def test_check_with_no_mode_flag_exits_1(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 1

    def test_check_all_failing_post_exits_1(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "bad-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```sql\nSELECT * FROM nonexistent\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--all"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_dry_run_always_exits_0(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "bad-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```sql\nSELECT * FROM nonexistent\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--all", "--dry-run"])
        assert result.exit_code == 0

    def test_verbose_shows_block_details(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all", "--verbose"])
        assert result.exit_code == 0
        assert "block" in result.output.lower()

    def test_summary_line_shows_counts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all"])
        assert "Done." in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_main.py -v
```

Expected: failures because `check` command doesn't exist yet

- [ ] **Step 3: Implement check command in main.py**

```python
# blog_validate/main.py
from pathlib import Path
from typing import Optional
import typer
from typing import Annotated
from blog_validate.config import load_config
from blog_validate.extractor import scan_posts, build_fixture_registry
from blog_validate.runner import (
    PostResult, get_changed_files, resolve_changed_posts, run_post,
)

app = typer.Typer(help="Validate code blocks in Hugo blog posts.")


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
                    typer.echo(f"  FAIL block {r.block.block_index} ({r.block.language}): {r.error}")
                elif verbose and r.status == "passed":
                    typer.echo(f"  PASS block {r.block.block_index} ({r.block.language})")
        if not post_result.passed:
            any_failed = True
    return any_failed


@app.command()
def check(
    all_posts: Annotated[bool, typer.Option("--all", help="Validate all posts")] = False,
    changed: Annotated[bool, typer.Option("--changed", help="Validate changed posts and fixture dependents")] = False,
    post: Annotated[Optional[str], typer.Option("--post", help="Validate a single post by slug")] = None,
    verbose: Annotated[bool, typer.Option("--verbose", "-v")] = False,
    dry_run: Annotated[bool, typer.Option("--dry-run", "-n")] = False,
) -> None:
    """Validate code blocks in blog posts."""
    if not any([all_posts, changed, post]):
        typer.echo("Error: specify --all, --changed, or --post <slug>", err=True)
        raise typer.Exit(code=1)

    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(config.root, config.blog.content_path, config.blog.post_file)
    fixture_registry = build_fixture_registry(all_post_blocks)
    helpers_path: Path | None = config.root / "blog-validate-helpers.py"
    if not helpers_path.exists():
        helpers_path = None

    if all_posts:
        posts_to_check = all_post_blocks
    elif changed:
        changed_files = get_changed_files(config.root)
        posts_to_check = resolve_changed_posts(
            changed_files, all_post_blocks, fixture_registry,
            config.root, config.blog.content_path, config.blog.post_file,
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
        run_post(p, fixture_registry, helpers_path=helpers_path, dry_run=dry_run, verbose=verbose)
        for p in posts_to_check
    ]

    any_failed = _print_results(results, verbose)
    passed = sum(1 for r in results if r.passed)
    typer.echo(f"\nDone. {passed}/{len(results)} posts passed.")

    if any_failed:
        raise typer.Exit(code=1)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
uv run pytest tests/test_main.py -v
```

Expected: 8 passed

- [ ] **Step 5: Confirm CLI works end-to-end against the real blog**

```bash
cd ~/projects/jamalhansen.com
blog-validate check --post advanced-sql-topics-sampler --verbose
```

Expected: post runs, SQL blocks execute against DuckDB

- [ ] **Step 6: Commit**

```bash
git add blog_validate/main.py tests/test_main.py
git commit -m "feat: add check command — --all, --changed, --post, --verbose, --dry-run"
```

---

## Task 12: CLI — list-fixtures and list-posts Commands

**Files:**
- Modify: `blog_validate/main.py`
- Modify: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests** (add to `tests/test_main.py`)

```python
class TestListCommands:
    def test_list_fixtures_with_no_fixtures(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-fixtures"])
        assert result.exit_code == 0
        assert "No named fixtures" in result.output

    def test_list_fixtures_shows_defined_fixtures(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "setup-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '<!-- test:fixture name="users-table" -->\n```sql\nCREATE TABLE users (id INT);\n```\n'
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["list-fixtures"])
        assert result.exit_code == 0
        assert "users-table" in result.output
        assert "setup-post" in result.output

    def test_list_posts_shows_all_posts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-posts"])
        assert result.exit_code == 0
        assert "my-post" in result.output

    def test_list_posts_shows_block_counts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-posts"])
        assert "1 block" in result.output or "blocks" in result.output
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
uv run pytest tests/test_main.py::TestListCommands -v
```

Expected: failures — commands don't exist yet

- [ ] **Step 3: Implement list-fixtures and list-posts** (add to `blog_validate/main.py`)

```python
@app.command("list-fixtures")
def list_fixtures() -> None:
    """Show all named fixtures and the posts that define and use them."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(config.root, config.blog.content_path, config.blog.post_file)
    fixture_registry = build_fixture_registry(all_post_blocks)

    if not fixture_registry:
        typer.echo("No named fixtures found.")
        return

    uses: dict[str, list[str]] = {name: [] for name in fixture_registry}
    for post in all_post_blocks:
        for b in post.blocks:
            if b.annotation.value == "use" and b.fixture_name in uses:
                uses[b.fixture_name].append(post.slug)

    for name, fixture_block in sorted(fixture_registry.items()):
        user_list = ", ".join(uses[name]) if uses[name] else "none"
        typer.echo(f"{name} ({fixture_block.language}) — defined in: {fixture_block.post_slug}")
        typer.echo(f"  used by: {user_list}")


@app.command("list-posts")
def list_posts() -> None:
    """Show all posts with code blocks and their annotation counts."""
    config = load_config(Path.cwd())
    all_post_blocks = scan_posts(config.root, config.blog.content_path, config.blog.post_file)

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
```

- [ ] **Step 4: Run all tests**

```bash
uv run pytest tests/ -v
```

Expected: all passed

- [ ] **Step 5: Commit**

```bash
git add blog_validate/main.py tests/test_main.py
git commit -m "feat: add list-fixtures and list-posts commands"
```

---

## Task 13: Pre-commit Hook and README

**Files:**
- Create: `scripts/hooks/pre-commit`
- Create: `README.md`

- [ ] **Step 1: Create pre-commit hook**

```bash
mkdir -p scripts/hooks
```

```bash
# scripts/hooks/pre-commit
#!/bin/bash
# Blog code block validator — pre-commit hook.
#
# Install into your blog repo:
#   cp /path/to/blog-code-block-validator/scripts/hooks/pre-commit .git/hooks/pre-commit
#   chmod +x .git/hooks/pre-commit
#
# Requires blog-validate installed:
#   uv tool install /path/to/blog-code-block-validator

blog-validate check --changed

if [ $? -ne 0 ]; then
    echo ""
    echo "Fix failing code blocks before committing."
    echo "To skip this check: git commit --no-verify"
    exit 1
fi
```

```bash
chmod +x scripts/hooks/pre-commit
```

- [ ] **Step 2: Run full test suite one final time**

```bash
uv run pytest tests/ -v
```

Expected: all passed

- [ ] **Step 3: Write README.md**

```markdown
# blog-code-block-validator

Validates code blocks in Hugo blog posts using inline annotations. Runs as a pre-commit hook.

## Installation

```bash
uv tool install git+ssh://git@github.com/jamalhansen/blog-code-block-validator.git
```

## Setup

Add `blog-validate.toml` to your blog repo root:

```toml
[blog]
content_path = "content/blog"
post_file = "index.md"

[sql]
backend = "duckdb"
```

Install the pre-commit hook:

```bash
cp /path/to/blog-code-block-validator/scripts/hooks/pre-commit .git/hooks/pre-commit
chmod +x .git/hooks/pre-commit
```

## Annotations

Place these HTML comments on the line immediately before a code fence:

| Annotation | Behavior |
|---|---|
| `<!-- test:skip -->` | Skip this block |
| `<!-- test:expected-failure -->` | Assert the block errors |
| `<!-- test:setup -->` | Run for side effects only |
| `<!-- test:syntax-only -->` | Parse only, don't execute |
| `<!-- test:assert -->` | Assert result is truthy |
| `<!-- test:fixture name="..." -->` | Define a named shared fixture |
| `<!-- test:use name="..." -->` | Inject a named fixture |

## CLI

```
blog-validate check --all
blog-validate check --changed       # pre-commit default
blog-validate check --post <slug>
blog-validate list-fixtures
blog-validate list-posts
```

## Shared Fixtures

Define a fixture once in any post:

```markdown
<!-- test:fixture name="customers-table" -->
```sql
CREATE TABLE customers (id INT, name VARCHAR);
INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob');
```
```

Reference it anywhere:

```markdown
<!-- test:use name="customers-table" -->
```sql
SELECT * FROM customers
```
```

## Helpers File

Add `blog-validate-helpers.py` at your blog root for reusable assertion helpers. It is automatically injected into Python execution context for every post:

```python
def assert_row_count(conn, table, n):
    actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert actual == n, f"Expected {n} rows in {table}, got {actual}"
```
```

- [ ] **Step 4: Commit**

```bash
git add scripts/hooks/pre-commit README.md
git commit -m "feat: add pre-commit hook and README"
```

- [ ] **Step 5: Push to GitHub**

```bash
git push origin main
```
```
