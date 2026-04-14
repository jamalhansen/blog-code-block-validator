# blog-code-block-validator — Activation Plan

Tool is complete (109 tests, 95% coverage). This plan covers activating it against the real blog.

---

## Step 1 — Install globally

```bash
uv tool install --editable ~/projects/blog-code-block-validator
blog-validate --help
```

## Step 2 — Dry run against a SQL series post

Pick a post with SQL and Python blocks and run:

```bash
blog-validate check --post content/blog/[series]/[slug]/index.md
```

Read the output. Any unannotated blocks that can't run will show as failures or skips.

## Step 3 — Add annotations

For each code block that needs context, add an annotation comment above the fence:

```markdown
<!-- blog-validate: skip reason="requires postgres" -->
```

```markdown
<!-- blog-validate: fixture="my-fixture" -->
```

See `blog-validate list-fixtures` and `blog-validate list-skips` for what's registered.

## Step 4 — Run across the full series

```bash
blog-validate check --all
```

Fix or annotate any remaining failures.

## Step 5 — Wire as pre-commit hook in blog repo

Add to `.pre-commit-config.yaml` or the Makefile in `~/projects/jamalhansen.com`.

---

## Status

- [x] Installed globally (`uv tool install --editable ~/projects/blog-code-block-validator`)
- [ ] Tested on one post
- [ ] Annotations added
- [ ] Full series run clean
- [ ] Pre-commit hook wired
