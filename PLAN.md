# blog-code-block-validator — Extension Plan

Work log: `SESSION.log` at project root. One entry per meaningful decision or deviation.

---

## Background

The tool works for flat Hugo post bundles (`content/blog/slug/index.md`). Two things break coverage:

1. **Series posts are invisible.** Hugo series live at `content/blog/series/slug/index.md` — one level deeper than `iterdir()` reaches. All 25 SQL series posts, Forging the Truth, vibe-coded series, etc. are silently skipped.
2. **Obsidian vault posts are unsupported.** Vault posts use descriptive filenames, not `index.md`, and are nested under `blog/series/[series]/posts/[slug]/`.

The goal is full coverage of every post on the blog — in both the vault (where posts are written) and Hugo (where they're published).

---

## Scope

### Feature 1 — Fix Hugo series discovery

**Change:** Replace `iterdir()` with `rglob(post_file)` in `scan_posts()`.

`rglob` finds `index.md` at any depth under `content/blog/`. Slug is always `path.parent.name` (the immediate parent directory). The series directory itself (`sql-for-python-developers/`) has no `index.md` and is never mistaken for a post.

No config change needed. Existing `blog-validate.toml` in `~/projects/jamalhansen.com` works as-is.

### Feature 2 — Vault layout

**Change:** Add `layout = "vault"` to config + extractor.

Vault posts are organized as: `blog/series/[series]/posts/[slug]/[descriptive-name].md`. Each slug directory contains exactly one post `.md` file (plus optional non-post files like `promo.md`).

Vault layout behavior:
- Walk all subdirectories under `content_path` recursively
- For each leaf directory, take the first `.md` not matching `exclude_patterns`
- Slug = leaf directory name

Config added to `~/vaults/BrainSync/blog-validate.toml`:

```toml
[blog]
content_path = "blog"
layout = "vault"
exclude_patterns = ["promo.md"]

[sql]
backend = "duckdb"
```

### Feature 3 — Coverage subcommand

**New command:** `blog-validate coverage`

Reports annotation coverage across all posts. Output:

```
Coverage report
───────────────────────────────────────────────
Posts with no code blocks:          12  (skipped — nothing to annotate)
Posts with only annotated blocks:    8  (fully covered)
Posts with unannotated blocks:       5  (needs attention)
Posts with failures:                 1  (fix required)

Unannotated posts:
  sql-for-python-developers/05-sql-thinks-in-sets-not-loops  3 unannotated blocks
  sql-for-python-developers/09-where-filtering-your-data     2 unannotated blocks
  ...

Skipped blocks by reason:
  test:skip              14
  test:expected-failure   3
  test:setup              6
```

Flags:
- `--unannotated` — list only posts with unannotated default blocks
- `--all` — include posts with no code blocks in output

Exit code: 0 always (coverage is informational, not a gate).

---

## Annotation strategy (post-validation)

Once the tool validates correctly against both locations:

1. Add annotations to Obsidian source posts (the single source of truth)
2. obsidian-hugo-bridge carries HTML comment annotations through to Hugo — they live in the markdown body, not frontmatter
3. Run `blog-validate check --all` in Hugo to confirm carry-through
4. Annotations in Hugo are never added directly — they live in the vault

This means the workflow is: **annotate in vault → publish → validate in Hugo**.

---

## Test plan

### Existing tests (keep)

109 unit tests in `tests/`. Keep all. Add unit tests as new code is added (extractor changes, vault layout, coverage command).

### New: functional test suite

Location: `tests/functional/`

These tests invoke the CLI via Typer's `CliRunner` against synthetic fixtures. They test behavior, not implementation. Each test class describes a feature.

#### Synthetic fixtures

Location: `tests/functional/fixtures/`

Build in `conftest.py` using `tmp_path`. No real post content is ever read or written by tests.

**Fixture: Hugo blog with flat + series posts**

```
hugo_blog/
├── blog-validate.toml
└── content/blog/
    ├── flat-post/
    │   └── index.md          # python block + sql block, no annotations
    ├── annotated-flat-post/
    │   └── index.md          # skip, expected-failure, setup, fixture, use
    ├── sql-series/
    │   ├── 01-intro/
    │   │   └── index.md      # sql block only
    │   └── 02-joins/
    │       └── index.md      # sql block + python block
    └── mixed-series/
        └── 01-post/
            └── index.md      # failing python block, expected-failure annotation
```

**Fixture: Obsidian vault**

```
obsidian_vault/
├── blog-validate.toml
└── blog/
    └── series/
        ├── sql-series/
        │   └── posts/
        │       ├── 01-intro/
        │       │   ├── intro-post.md     # sql block
        │       │   └── promo.md          # should be excluded
        │       └── 02-joins/
        │           └── joins-post.md     # sql + python blocks
        └── another-series/
            └── posts/
                └── 01-first/
                    └── first-post.md     # python block
```

**Fixture: Annotation carry-through**

A pair of files where the Obsidian source and its Hugo equivalent share the same code blocks and annotations. Used to verify annotations survive the bridge (static test — no actual bridge invocation).

#### Functional test classes

```
tests/functional/
├── conftest.py               # fixture factories
├── test_hugo_discovery.py    # Feature: Hugo post discovery
├── test_vault_discovery.py   # Feature: Vault post discovery
├── test_annotation_types.py  # Feature: All annotation types work correctly
├── test_coverage_command.py  # Feature: Coverage reporting
├── test_carry_through.py     # Feature: Annotations survive Hugo publish
└── test_regression.py        # Regression: specific issues that were broken
```

**`test_hugo_discovery.py`**

| Test | What it proves |
|---|---|
| `test_flat_posts_are_discovered` | Existing behavior preserved |
| `test_series_posts_are_discovered` | BUG FIX: series posts now found |
| `test_series_dir_not_treated_as_post` | Series container dir is not a false positive |
| `test_deeply_nested_posts_discovered` | rglob handles 3+ levels |
| `test_list_posts_shows_series_posts` | CLI output includes series slugs |
| `test_check_all_includes_series_posts` | check --all runs series posts |

**`test_vault_discovery.py`**

| Test | What it proves |
|---|---|
| `test_vault_posts_are_discovered` | Vault layout finds descriptive-filename posts |
| `test_promo_files_excluded` | `promo.md` is not treated as a post |
| `test_exclude_patterns_respected` | Custom exclude patterns work |
| `test_vault_slug_is_directory_name` | Slug derived from parent dir, not filename |
| `test_vault_check_runs_sql_blocks` | SQL blocks in vault posts execute |
| `test_vault_list_posts_output` | CLI shows vault posts correctly |

**`test_annotation_types.py`**

| Test | What it proves |
|---|---|
| `test_skip_block_not_executed` | skip annotation prevents execution |
| `test_expected_failure_passes_on_error` | block that errors is a PASS |
| `test_expected_failure_fails_on_success` | block that succeeds is a FAIL |
| `test_setup_block_runs_for_side_effects` | setup block executes, not counted |
| `test_fixture_defined_and_used` | named fixture available across blocks |
| `test_syntax_only_parsed_not_executed` | syntax-only checks parse, skips run |
| `test_unannotated_sql_executes` | bare sql block runs and passes on valid SQL |
| `test_unannotated_python_executes` | bare python block runs |

**`test_coverage_command.py`**

| Test | What it proves |
|---|---|
| `test_coverage_exits_0_always` | never a gate, always informational |
| `test_coverage_counts_unannotated` | correctly identifies unannotated blocks |
| `test_coverage_counts_annotated` | correctly counts covered blocks |
| `test_coverage_unannotated_flag` | --unannotated filters output |
| `test_coverage_shows_skip_breakdown` | skip reason counts are accurate |
| `test_coverage_excludes_no_block_posts` | posts with no blocks not in unannotated list |

**`test_carry_through.py`**

| Test | What it proves |
|---|---|
| `test_skip_annotation_survives_bridge` | `<!-- test:skip -->` in vault md recognized in Hugo md |
| `test_fixture_annotation_survives_bridge` | named fixture annotation carries through |
| `test_expected_failure_survives_bridge` | expected-failure carries through |

These tests use static paired fixtures (vault source + simulated Hugo output). No bridge invocation.

**`test_regression.py`**

| Test | What it proves |
|---|---|
| `test_series_posts_were_invisible` | Reproduces original bug, confirms fix |
| `test_ollama_inline_script_skipped` | PEP 723 block with skip annotation passes |

---

## Success criteria

The plan is complete when all of the following are true:

1. `blog-validate list-posts` run from `~/projects/jamalhansen.com` lists all posts in every series — SQL series (25 posts), Forging the Truth, vibe-coded series, tsql-tuesday, and all flat posts.
2. `blog-validate list-posts` run from `~/vaults/BrainSync` lists all vault posts across all series.
3. `blog-validate check --all` completes without errors in both locations (failures allowed; crashes and missing posts are not).
4. `blog-validate coverage` produces a valid report in both locations showing unannotated block counts.
5. An annotation written in an Obsidian source post is recognized by `blog-validate` when run against the corresponding Hugo post — confirmed by `test_carry_through.py` tests.
6. All 109 existing unit tests pass.
7. All functional tests in `tests/functional/` pass.
8. No real post content files are read or written by any test.
9. Test coverage report (`uv run pytest --cov`) shows which source files lack coverage — used to identify gaps, not as a hard threshold.

---

## Files to create or modify

| File | Change |
|---|---|
| `blog_validate/extractor.py` | Replace `iterdir()` with `rglob(post_file)` in bundle layout; add vault layout handler |
| `blog_validate/config.py` | Add `layout: str = "bundle"`, `exclude_patterns: list[str] = []` to BlogConfig |
| `blog_validate/main.py` | Add `coverage` subcommand |
| `tests/test_extractor.py` | Add unit tests for rglob behavior, vault layout, exclude patterns |
| `tests/functional/conftest.py` | Synthetic fixture factories |
| `tests/functional/test_hugo_discovery.py` | Hugo discovery feature tests |
| `tests/functional/test_vault_discovery.py` | Vault discovery feature tests |
| `tests/functional/test_annotation_types.py` | Annotation behavior feature tests |
| `tests/functional/test_coverage_command.py` | Coverage command feature tests |
| `tests/functional/test_carry_through.py` | Annotation carry-through feature tests |
| `tests/functional/test_regression.py` | Regression tests for known bugs |
| `~/projects/jamalhansen.com/blog-validate.toml` | No change needed (rglob is automatic) |
| `~/vaults/BrainSync/blog-validate.toml` | New file — vault layout config |

Real content files (`~/projects/jamalhansen.com/content/`, `~/vaults/BrainSync/blog/`) are not touched during implementation or testing.

---

## Out of scope

- Adding annotations to real posts (done separately, after tool validates)
- Pre-commit hook wiring (separate step after full coverage confirmed)
- Supporting layouts other than `bundle` and `vault`
