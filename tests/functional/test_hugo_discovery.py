import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_flat_posts_are_discovered(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "flat-post" in result.stdout
    assert "annotated-flat-post" in result.stdout

def test_series_posts_are_discovered(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "02-joins" in result.stdout
    assert "01-post" in result.stdout

def test_list_posts_shows_series_posts(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["list-posts"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "02-joins" in result.stdout

def test_check_all_includes_series_posts(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["check", "--all"])
    assert result.exit_code == 0
    assert "01-intro" in result.stdout
    assert "02-joins" in result.stdout
