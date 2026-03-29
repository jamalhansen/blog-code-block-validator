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

**Flags for `check`:**

| Flag | Short | Description |
|---|---|---|
| `--all` | | Validate all posts |
| `--changed` | | Validate staged posts + fixture dependents |
| `--post <slug>` | | Validate a single post by slug |
| `--verbose` | `-v` | Show per-block pass/fail detail |
| `--dry-run` | `-n` | Skip execution, report all as skipped |

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

When a fixture post changes, all posts that use its fixtures are automatically included in `--changed` validation.

## Helpers File

Add `blog-validate-helpers.py` at your blog root for reusable assertion helpers. It is automatically injected into the Python execution context for every post:

```python
def assert_row_count(conn, table, n):
    actual = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    assert actual == n, f"Expected {n} rows in {table}, got {actual}"
```

## Project Structure

```
blog_validate/
├── config.py          # Load blog-validate.toml, walk up directories
├── extractor.py       # Parse annotations, extract blocks, scan posts
├── runner.py          # Run blocks, resolve changed posts
├── main.py            # Typer CLI
└── languages/
    ├── base.py        # AnnotationType, CodeBlock, Validator ABC
    ├── python.py      # Python syntax check + exec
    ├── sql.py         # DuckDB syntax check + exec + assert
    └── __init__.py    # VALIDATORS dict, make_context()
scripts/
└── hooks/
    └── pre-commit     # Pre-commit hook for your blog repo
```
