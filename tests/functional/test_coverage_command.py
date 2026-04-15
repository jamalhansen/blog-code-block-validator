import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_coverage_exits_0_always(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["coverage"])
    assert result.exit_code == 0

def test_coverage_counts_unannotated(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["coverage"])
    assert "Posts with unannotated blocks:       3" in result.stdout

def test_coverage_unannotated_flag(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["coverage", "--unannotated"])
    assert result.exit_code == 0
    assert "flat-post" in result.stdout
    assert "01-intro" in result.stdout
    assert "annotated-flat-post" not in result.stdout

def test_coverage_shows_skip_breakdown(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["coverage"])
    assert "skip" in result.stdout
    assert "1" in result.stdout
