import json
import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_vault_posts_are_discovered(obsidian_vault_factory):
    vault_root = obsidian_vault_factory()
    os.chdir(vault_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "02-joins" in result.stdout
    assert "01-first" in result.stdout

def test_promo_files_excluded(obsidian_vault_factory):
    vault_root = obsidian_vault_factory()
    os.chdir(vault_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "01-intro: 1 block" in result.stdout

def test_vault_slug_is_directory_name(obsidian_vault_factory):
    vault_root = obsidian_vault_factory()
    os.chdir(vault_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "intro-post" not in result.stdout

def test_vault_check_runs_sql_blocks(obsidian_vault_factory):
    vault_root = obsidian_vault_factory()
    os.chdir(vault_root)

    result = runner.invoke(app, ["check", "--all"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "PASS" in result.stdout


def test_loose_files_under_posts_are_each_their_own_post(obsidian_vault_factory):
    """Forging the Truth keeps ~20 short posts as loose .md files directly in
    posts/. They used to collapse into a single post with slug "posts" and only
    the first file ever ran."""
    vault_root = obsidian_vault_factory()
    posts = vault_root / "blog" / "series" / "sql-series" / "posts"
    (posts / "03a-quick-tip.md").write_text("```sql\nSELECT 3;\n```")
    (posts / "03b-other-tip.md").write_text("```sql\nSELECT 4;\n```")
    os.chdir(vault_root)

    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "03a-quick-tip: 1 block" in result.stdout
    assert "03b-other-tip: 1 block" in result.stdout
    assert "posts:" not in result.stdout


def test_notes_without_a_posts_ancestor_are_not_posts(obsidian_vault_factory):
    """Series index notes, ideas/ and planning docs sit next to posts in the
    vault; they are not posts and their code must never be executed."""
    vault_root = obsidian_vault_factory()
    blog = vault_root / "blog"
    (blog / "series" / "sql-series" / "SQL Series Index.md").write_text("```python\nraise SystemExit(1)\n```")
    (blog / "ideas").mkdir()
    (blog / "ideas" / "Some Idea.md").write_text("```python\n1/0\n```")
    (blog / "content-strategy-plan.md").write_text("```python\n1/0\n```")
    os.chdir(vault_root)

    result = runner.invoke(app, ["check", "--all"])
    assert result.exit_code == 0
    for not_a_post in ("sql-series:", "ideas:", "Some Idea", "blog:", "content-strategy-plan"):
        assert not_a_post not in result.stdout


def _vault_with_statuses(vault_root):
    posts = vault_root / "blog" / "series" / "sql-series" / "posts"
    (posts / "03-dropped.md").write_text("---\nstatus: dropped\n---\n```python\n1/0\n```")
    (posts / "04-outline.md").write_text("---\ntitle: X\nstatus: 'outline'\n---\n```python\n1/0\n```")
    (posts / "05-draft.md").write_text("---\nstatus: draft\n---\n```python\nassert True\n```")
    with (vault_root / "blog-validate.toml").open("a") as f:
        f.write('skip_statuses = ["dropped", "outline"]\n')
    return vault_root


def test_skip_statuses_are_not_run_but_are_reported(obsidian_vault_factory):
    vault_root = _vault_with_statuses(obsidian_vault_factory())
    os.chdir(vault_root)

    result = runner.invoke(app, ["check", "--all", "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    ran = {p["slug"] for p in data["posts"]}
    assert "05-draft" in ran
    assert "03-dropped" not in ran and "04-outline" not in ran
    assert data["summary"]["posts_skipped_by_status"] == 2
    assert {"slug": "04-outline", "status": "outline"} in data["skipped_by_status"]


def test_skip_statuses_apply_to_coverage(obsidian_vault_factory):
    vault_root = _vault_with_statuses(obsidian_vault_factory())
    os.chdir(vault_root)

    data = json.loads(runner.invoke(app, ["coverage", "--json"]).stdout)
    assert data["posts_skipped_by_status"] == 2


def test_explicit_post_runs_regardless_of_status(obsidian_vault_factory):
    vault_root = _vault_with_statuses(obsidian_vault_factory())
    os.chdir(vault_root)

    result = runner.invoke(app, ["check", "--post", "03-dropped"])
    assert result.exit_code == 1
    assert "03-dropped" in result.stdout


def test_dated_posts_tree_supports_both_shapes(obsidian_vault_factory):
    """blog/posts/<YYYY>/<MM>/ holds both loose files and bundle directories."""
    vault_root = obsidian_vault_factory()
    month = vault_root / "blog" / "posts" / "2026" / "04"
    month.mkdir(parents=True)
    (month / "a-loose-dated-post.md").write_text("```sql\nSELECT 1;\n```")
    (month / "a-bundled-post").mkdir()
    (month / "a-bundled-post" / "the-post.md").write_text("```sql\nSELECT 1;\n```")
    os.chdir(vault_root)

    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "a-loose-dated-post: 1 block" in result.stdout
    assert "a-bundled-post: 1 block" in result.stdout
    assert "04:" not in result.stdout
    assert "the-post" not in result.stdout
