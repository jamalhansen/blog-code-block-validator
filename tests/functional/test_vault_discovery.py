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
