import os
import textwrap
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()


def test_check_accepts_explicit_config_path(tmp_path):
    """--config points at a toml file outside the cwd; content_path resolves relative to it."""
    project_dir = tmp_path / "project"
    project_dir.mkdir()
    os.chdir(project_dir)

    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    posts_dir = config_dir / "posts"
    posts_dir.mkdir()
    (posts_dir / "hello.md").write_text(textwrap.dedent("""
        # Hello
        ```python
        assert 1 + 1 == 2
        ```
    """))
    (config_dir / "external.toml").write_text(textwrap.dedent("""
        [blog]
        content_path = "posts"
        layout = "flat"
    """))

    result = runner.invoke(app, ["check", "--all", "--config", str(config_dir / "external.toml")])
    assert result.exit_code == 0
    assert "hello" in result.stdout


def test_annotation_drift_lists_differences_both_ways(tmp_path):
    """Drift runs both ways: skips only in the published copy, asserts only in
    the vault draft. Posts that exist in just one place aren't drift."""
    import json as _json

    def make(root, layout, posts):
        root.mkdir()
        (root / "blog-validate.toml").write_text(f"[blog]\ncontent_path = 'posts'\nlayout = '{layout}'\n")
        (root / "posts").mkdir()
        for slug, body in posts.items():
            (root / "posts" / f"{slug}.md").write_text(body)

    make(tmp_path / "blog", "flat", {
        "shared": "<!-- test:skip -->\n```python\nx = 1\n```\n```python\ny = 2\n```\n",
        "same": "<!-- test:skip -->\n```python\nx = 1\n```\n",
        "blog-only": "```python\nx = 1\n```\n",
    })
    make(tmp_path / "vault", "flat", {
        "shared": "```python\nx = 1\n```\n<!-- test:assert -->\n```python\ny == 2\n```\n",
        "same": "<!-- test:skip -->\n```python\nx = 1\n```\n",
    })
    os.chdir(tmp_path / "blog")

    result = runner.invoke(app, ["annotation-drift", "--against", str(tmp_path / "vault" / "blog-validate.toml"), "--json"])
    assert result.exit_code == 0
    data = _json.loads(result.stdout)
    assert data["shared_posts"] == 2
    assert data["drifted"] == [
        {"slug": "shared", "here": 1, "there": 1, "only_here": ["skip"], "only_there": ["assert"]}
    ]

    text = runner.invoke(app, ["annotation-drift", "--against", str(tmp_path / "vault" / "blog-validate.toml")])
    assert "2 posts in both places, 1 with different annotations" in text.stdout


def test_content_path_expands_tilde(tmp_path, monkeypatch):
    """content_path starting with ~ should expand to the home directory, not join literally."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setenv("HOME", str(fake_home))

    posts_dir = fake_home / "notes" / "patterns"
    posts_dir.mkdir(parents=True)
    (posts_dir / "note.md").write_text(textwrap.dedent("""
        # Note
        ```python
        assert True
        ```
    """))

    project_dir = tmp_path / "project"
    project_dir.mkdir()
    (project_dir / "blog-validate.toml").write_text(textwrap.dedent("""
        [blog]
        content_path = "~/notes/patterns"
        layout = "flat"
    """))
    os.chdir(project_dir)

    result = runner.invoke(app, ["check", "--all"])
    assert result.exit_code == 0
    assert "note" in result.stdout
