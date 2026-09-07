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
