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
# "bundle" (default) for Hugo leaf bundles (dir/index.md)
# "flat" for simple markdown files (dir/*.md)
layout = "bundle"
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
| `<!-- test:setup -->` | Run for side effects only (also supports `:start` and `:end` for multi-line cleanup) |
| `<!-- test:syntax-only -->` | Parse only, don't execute |
| `<!-- test:assert -->` | Assert result is truthy (also supports `:start` and `:end`) |
| `<!-- test:fixture name="..." -->` | Define a named shared fixture |
| `<!-- test:use name="..." -->` | Inject a named fixture |

## Semantic Markers for Cleanup

To keep patterns clean for publishing, you can use semantic markers for multi-line test blocks:

```markdown
<!-- test:setup:start -->
```python
# Test-only setup code
```
<!-- test:setup:end -->

<!-- test:assert:start -->
```python
# Test-only assertion code
```
<!-- test:assert:end -->
```

These markers are recognized by the validator but provide clear anchors for automated removal before publishing:

```bash
# Example cleanup
sed -i '' '/<!-- test:.*:start -->/,/<!-- test:.*:end -->/d' post.md
```

## CLI

```
blog-validate check --all
blog-validate check --changed       # pre-commit default
blog-validate check --post <slug>
blog-validate list-fixtures
blog-validate list-posts
blog-validate list-skips            # audit all skipped blocks
blog-validate test-guide --post <slug>   # testing checklist, no execution
blog-validate test-guide --all
blog-validate stats                      # block count by language across all posts
blog-validate find <language>            # posts containing blocks of a given language
```

**Flags for `check`:**

| Flag | Short | Description |
|---|---|---|
| `--all` | | Validate all posts |
| `--changed` | | Validate staged posts + fixture dependents |
| `--post <slug>` | | Validate a single post by slug |
| `--verbose` | `-v` | Show per-block pass/fail detail |
| `--dry-run` | `-n` | Skip execution, report all as skipped |
| `--config <path>` | | Load an alternate `blog-validate.toml` instead of walking up from cwd (e.g. for validating a config outside the current repo) |

```bash
# Validate a source outside this repo, e.g. newsletter patterns
blog-validate check --all --config configs/newsletter.toml
# same thing via the Makefile
make validate-newsletter
```

## Shared Fixtures

Define a fixture once in any post:
...
When a fixture post changes, all posts that use its fixtures are automatically included in `--changed` validation.

## Python Dependencies

`blog-validate` supports blog posts that import external Python modules (e.g., `pytest`, `ollama`, `local-first-common`).

1. **Local Virtual Environment**: If a `.venv` directory exists in your blog repo root, `blog-validate` will automatically include its `site-packages` in the Python search path. This allows you to use any modules installed in your project's environment.
2. **Configuration**: You can declare required dependencies in `blog-validate.toml` to get warnings if they are missing from your environment:

```toml
[python]
dependencies = ["pytest", "ollama", "local-first-common"]
```

## Bash Support

`blog-validate` supports terminal snippets marked as `bash` or `sh`.

- **Isolation**: Each post's bash commands run in a temporary directory. Files created during execution are automatically deleted.
- **Syntax Check**: Uses `bash -n` to verify snippet syntax.
- **Execution**: Runs commands via `subprocess.run(shell=True)`.

## TOML & Markdown Support

`blog-validate` supports linting and validation for `toml` and `markdown` blocks.

- **TOML**: Uses Python's built-in `tomllib` to verify that snippets are well-formed.
- **Markdown**: Uses `pymarkdownlnt` to lint snippets. It automatically ignores noisy rules for snippets (like line length and missing first-line headers).

## Helpers Directory

Add a `blog-validate-helpers/` directory at your blog repo root for reusable setup fixtures. File extension determines language (`.sql` → SQL, `.py` → Python).

**Named helpers** — opt in per post with a `<!-- test:needs: ... -->` comment after the frontmatter closing `---`:

```markdown
<!-- test:needs: customers, orders -->
```

The comment is invisible to readers. The named helpers run before the post's blocks, setting up tables or state the post's SQL expects.

**Auto-run helpers** — prefix a filename with `_` to run it before every post automatically:

```
blog-validate-helpers/
├── _base.sql           # auto-run before every post
├── customers.sql       # opt-in: <!-- test:needs: customers -->
└── orders.sql          # opt-in: <!-- test:needs: orders -->
```

Each helper file should use `CREATE TABLE IF NOT EXISTS` for idempotency.

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
