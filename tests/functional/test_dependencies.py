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
    # Typer/CliRunner might capture stdout differently
    assert "Warning: Missing dependencies declared in blog-validate.toml: nonexistent-module" in result.stdout
