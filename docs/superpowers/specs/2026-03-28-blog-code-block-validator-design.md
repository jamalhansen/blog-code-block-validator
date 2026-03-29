# Blog Code Block Validator — Design Spec

**Date:** 2026-03-28
**Repo:** git@github.com:jamalhansen/blog-code-block-validator.git
**Status:** Approved, ready for implementation

---

## Overview

A standalone CLI tool that extracts annotated code blocks from Hugo blog posts and validates them — checking syntax, executing them, and asserting expected outcomes. Runs as a pre-commit hook on the blog repo, validating changed posts and any posts that depend on their shared fixtures.

Replaces the series-specific `sql-for-python-devs` test repo with a generic, annotation-driven system that works across all blog posts and all languages.

---

## Architecture

```
blog-code-block-validator/
├── blog_validate/
│   ├── main.py           # Typer CLI entry point
│   ├── extractor.py      # parse markdown, extract annotated blocks, build fixture index
│   ├── runner.py         # resolve deps, build context, execute, report
│   └── languages/
│       ├── __init__.py   # VALIDATORS dict
│       ├── base.py       # abstract Validator base class
│       ├── python.py     # Python validator
│       └── sql.py        # SQL validator (DuckDB)
├── tests/
├── scripts/
│   └── hooks/
│       └── pre-commit    # canonical hook for blog repo installation
├── pyproject.toml
├── README.md
└── blog-validate.toml    # example config (not used here — lives in blog repo)
```

---

## Annotation Format

HTML comments placed on the line immediately before a fenced code block. Invisible to blog readers. No annotation = default behavior (execute and assert no error).

| Annotation | Behavior |
|---|---|
| `<!-- test:skip -->` | Skip this block entirely |
| `<!-- test:expected-failure -->` | Assert the block raises an error |
| `<!-- test:setup -->` | Run for side effects; no result assertion |
| `<!-- test:syntax-only -->` | Parse/compile check only; do not execute |
| `<!-- test:assert -->` | Run as an assertion — failure raises test error (see below) |
| `<!-- test:fixture name="<name>" -->` | Define a named shared fixture |
| `<!-- test:use name="<name>" -->` | Inject a named fixture before this block |

### Assert blocks

**Python**: `exec()`'d normally — `assert` statements or any raised exception counts as failure. Helper functions from `blog-validate-helpers.py` are available (see Config).

**SQL**: query must return a single truthy value. Use boolean expressions:
```sql
SELECT COUNT(*) = 10 FROM customers
```

### Examples

```markdown
<!-- test:expected-failure -->
```sql
SELECT * FROM nonexistent_table
```

<!-- test:fixture name="customers-table" -->
```sql
CREATE TABLE customers (id INT, name VARCHAR);
INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob');
```

<!-- test:use name="customers-table" -->
```sql
SELECT * FROM customers WHERE id = 1
```

<!-- test:assert -->
```sql
SELECT COUNT(*) = 2 FROM customers
```

<!-- test:assert -->
```python
assert_row_count(conn, "customers", 2)
```
```

---

## Fixture System

**Two scopes:**

**Local setup** — `<!-- test:setup -->` blocks within a post run in document order before any default/test blocks. Implicit context for that post; no reference needed.

**Named shared fixtures** — `<!-- test:fixture name="..." -->` blocks are collected from all posts at startup into a fixture registry (name → code + language). Any post references them with `<!-- test:use name="..." -->`.

Named fixtures can be defined in any post — the harness finds them wherever they're annotated.

Named fixtures must be side-effect-only (CREATE TABLE, INSERT, etc.) — no assertions or output.

**Execution order per post:**

All annotations are processed in document order. A `<!-- test:use -->` injects the named fixture at its position in the document — not hoisted to the top. This means a fixture can be injected between two setup blocks if needed, and only subsequent blocks can depend on it.

**Execution context:**

- SQL: a fresh in-memory DuckDB connection shared across all blocks in the post
- Python: a shared `globals()` dict across all blocks in the post

---

## CLI

Entry point: `main.py` using Typer.

```
blog-validate check --all                  # validate every post
blog-validate check --changed              # changed posts + dependents (pre-commit default)
blog-validate check --post <slug>          # single post by slug
blog-validate list-fixtures                # show all named fixtures and defining posts
blog-validate list-posts                   # show all posts, block counts, annotations
```

**Standard flags on `check`:**
- `--verbose` / `-v` — show per-block progress
- `--dry-run` / `-n` — show what would run without executing

**`--changed` resolution:**
1. Get staged files from `git diff --cached --name-only`
2. Filter to files under `content_path`
3. For each changed file: if it defines named fixtures, add all posts that reference those fixtures
4. Run the resolved set

---

## Config (`blog-validate.toml` at blog root)

```toml
[blog]
content_path = "content/blog"
post_file = "index.md"

[sql]
backend = "duckdb"

[validate]
default_language_behavior = "skip"   # skip | syntax-only for unknown languages
helpers_file = "blog-validate-helpers.py"  # optional; auto-exec'd into Python globals for every post
```

The helpers file is optional. If present, it is executed into the shared Python globals context before any blocks run in a post. Use it for reusable assertion helpers:

```python
# blog-validate-helpers.py
def assert_row_count(conn, table, n):
    actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert actual == n, f"Expected {n} rows in {table}, got {actual}"
```

`conn` is automatically available in Python execution contexts — injected by the runner from the shared `ExecutionContext`.

Tool finds `blog-validate.toml` by walking up from the current directory.

---

## Language Validators

```python
# base.py
class Validator:
    language: str

    def syntax_check(self, code: str) -> None:
        ...   # raise ValidationError on failure

    def execute(self, code: str, context: ExecutionContext) -> None:
        ...   # raise ValidationError on failure
```

`ExecutionContext` carries shared state across blocks in a post (DuckDB connection for SQL, `globals()` dict for Python).

**Python**: `ast.parse()` for syntax; `exec()` into shared globals for execution.
**SQL**: DuckDB parse API for syntax; `conn.execute()` for execution. Schema persists across blocks via shared connection.

**Adding a language**: create `languages/<lang>.py`, implement `syntax_check` and `execute`, register in `VALIDATORS` dict. No changes to runner or extractor.

```python
# languages/__init__.py
VALIDATORS: dict[str, Validator] = {
    "python": PythonValidator(),
    "sql": SQLValidator(),
}
```

---

## Pre-commit Integration

Canonical hook at `scripts/hooks/pre-commit` in this repo. Installed into the blog repo's `.git/hooks/pre-commit`.

```bash
#!/bin/bash
blog-validate check --changed
if [ $? -ne 0 ]; then
    echo "Fix failing code blocks before committing."
    echo "To skip: git commit --no-verify"
    exit 1
fi
```

---

## Standards Alignment

Follows conventions from `~/projects/local-first/local-first-common/STANDARDS.md` where applicable:
- Typer for CLI (`@app.command()`)
- `--verbose` / `-v`, `--dry-run` / `-n`
- `main.py` as entry point

LLM-specific standards (`--no-llm`, `--provider`, `--model`, run tracking) do not apply — this tool makes no LLM calls.

---

## Migration from `sql-for-python-devs`

1. Annotate existing SQL for Python Devs posts with appropriate `<!-- test:* -->` comments (replacing the hardcoded `EXPECTED_FAILURES`, `SETUP_SCRIPTS`, `CODE_SNIPPETS` sets)
2. Move shared sample data setup into named fixtures
3. Install new pre-commit hook on blog repo
4. Retire the `sql-for-python-devs` pre-push hook

---

## Out of Scope

- Non-Hugo blog structures (configurable defaults only)
- LLM-based validation
- Non-DuckDB SQL backends (extensible but not implemented)
- Parallel test execution
