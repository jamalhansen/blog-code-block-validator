import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_series_posts_were_invisible(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert "01-intro" in result.stdout
    assert "02-joins" in result.stdout
    assert "01-post" in result.stdout

def test_ollama_inline_script_skipped(tmp_path):
    blog_root = tmp_path / "ollama"
    blog_root.mkdir()
    (blog_root / "blog-validate.toml").write_text("[blog]\nlayout='bundle'\ncontent_path='content/blog'")
    post_dir = blog_root / "content" / "blog" / "ollama-post"
    post_dir.mkdir(parents=True)
    
    content = """
    # Ollama Post
    
    <!-- test:skip -->
    ```python
    # /// script
    # dependencies = ["ollama"]
    # ///
    import ollama
    print("hi")
    ```
    """
    (post_dir / "index.md").write_text(content)
    
    os.chdir(blog_root)
    result = runner.invoke(app, ["check", "--all"])
    assert result.exit_code == 0
    assert "1–" in result.stdout
