import os
import sys
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_venv_discovery(tmp_path):
    # 1. Setup a blog with a .venv and a post that needs a module
    blog_root = tmp_path / "blog"
    blog_root.mkdir()
    (blog_root / "blog-validate.toml").write_text("[blog]\ncontent_path='.'\nlayout='bundle'")
    
    # Create a fake .venv/lib/python3.12/site-packages
    # Use current python version to be safe
    v = sys.version_info
    sp_path = blog_root / ".venv" / "lib" / f"python{v.major}.{v.minor}" / "site-packages"
    sp_path.mkdir(parents=True)
    
    # Create a dummy module in that site-packages
    (sp_path / "dummy_module.py").write_text("VERSION = '1.2.3'")
    
    post_dir = blog_root / "post"
    post_dir.mkdir()
    content = """---
title: Test
slug: test
---
```python
import dummy_module
print(f"Dummy version: {dummy_module.VERSION}")
```
"""
    (post_dir / "index.md").write_text(content)
    
    os.chdir(blog_root)
    # Clear sys.path of any previous runs if necessary, but CliRunner should be fresh-ish
    # Actually setup_environment will add it
    
    result = runner.invoke(app, ["check", "--all", "--verbose"])
    assert result.exit_code == 0
    assert "Dummy version: 1.2.3" in result.stdout

def test_dependency_warning(tmp_path):
    blog_root = tmp_path / "blog_warn"
    blog_root.mkdir()
    (blog_root / "blog-validate.toml").write_text("[blog]\ncontent_path='.'\n[python]\ndependencies=['nonexistent-module']")
    
    os.chdir(blog_root)
    result = runner.invoke(app, ["check", "--all"])
    # The warning goes to stderr (so --json stays clean); result.output has both streams
    assert "Warning: Missing dependencies declared in blog-validate.toml: nonexistent-module" in result.output


def test_venv_from_config_points_outside_the_config_root(tmp_path):
    """[python] venv lets a config in one place (configs/vault.toml) borrow the
    site-packages of a project that lives somewhere else (the blog repo)."""
    v = sys.version_info
    other_project = tmp_path / "other-project"
    sp_path = other_project / ".venv" / "lib" / f"python{v.major}.{v.minor}" / "site-packages"
    sp_path.mkdir(parents=True)
    (sp_path / "borrowed_module.py").write_text("VERSION = '4.5.6'")

    config_root = tmp_path / "configs"
    config_root.mkdir()
    (config_root / "post").mkdir()
    (config_root / "post" / "index.md").write_text(
        "```python\nimport borrowed_module\nprint(f'Borrowed: {borrowed_module.VERSION}')\n```\n"
    )
    (config_root / "blog-validate.toml").write_text(
        f"[blog]\ncontent_path='.'\nlayout='bundle'\n[python]\nvenv='{other_project / '.venv'}'\n"
    )

    os.chdir(config_root)
    result = runner.invoke(app, ["check", "--all", "--verbose"])
    assert result.exit_code == 0
    assert "Borrowed: 4.5.6" in result.stdout
