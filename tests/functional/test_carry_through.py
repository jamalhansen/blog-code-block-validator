import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_skip_annotation_survives_bridge(tmp_path):
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    (vault_root / "blog-validate.toml").write_text("[blog]\nlayout='vault'\ncontent_path='blog'")
    post_dir = vault_root / "blog" / "my-post"
    post_dir.mkdir(parents=True)
    content = "<!-- test:skip -->\n```python\nprint('skip me')\n```"
    (post_dir / "my-post.md").write_text(content)
    
    os.chdir(vault_root)
    result = runner.invoke(app, ["check", "--all"])
    assert "skipped=1" in result.stdout
    
    hugo_root = tmp_path / "hugo"
    hugo_root.mkdir()
    (hugo_root / "blog-validate.toml").write_text("[blog]\nlayout='bundle'\ncontent_path='content/blog'")
    hugo_post_dir = hugo_root / "content" / "blog" / "my-post"
    hugo_post_dir.mkdir(parents=True)
    (hugo_post_dir / "index.md").write_text(content)
    
    os.chdir(hugo_root)
    result = runner.invoke(app, ["check", "--all"])
    assert "skipped=1" in result.stdout

def test_expected_failure_survives_bridge(tmp_path):
    content = "<!-- test:expected-failure -->\n```python\n1/0\n```"
    
    vault_root = tmp_path / "vault_ef"
    vault_root.mkdir()
    (vault_root / "blog-validate.toml").write_text("[blog]\nlayout='vault'\ncontent_path='blog'")
    post_dir = vault_root / "blog" / "ef-post"
    post_dir.mkdir(parents=True)
    (post_dir / "ef-post.md").write_text(content)
    
    os.chdir(vault_root)
    result = runner.invoke(app, ["check", "--all"])
    assert "[PASS] ef-post" in result.stdout
    
    hugo_root = tmp_path / "hugo_ef"
    hugo_root.mkdir()
    (hugo_root / "blog-validate.toml").write_text("[blog]\nlayout='bundle'\ncontent_path='content/blog'")
    hugo_post_dir = hugo_root / "content" / "blog" / "ef-post"
    hugo_post_dir.mkdir(parents=True)
    (hugo_post_dir / "index.md").write_text(content)
    
    os.chdir(hugo_root)
    result = runner.invoke(app, ["check", "--all"])
    assert "[PASS] ef-post" in result.stdout
