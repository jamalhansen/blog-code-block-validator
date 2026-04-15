import os
from typer.testing import CliRunner
from blog_validate.main import app

runner = CliRunner()

def test_skip_block_not_executed(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["check", "--post", "annotated-flat-post"])
    assert result.exit_code == 0
    assert "skipped=2" in result.stdout

def test_expected_failure_passes_on_error(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["check", "--post", "annotated-flat-post"])
    assert result.exit_code == 0
    assert "[PASS] annotated-flat-post" in result.stdout

def test_setup_block_runs_for_side_effects(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["check", "--post", "annotated-flat-post"])
    assert result.exit_code == 0
    assert "passed=2" in result.stdout

def test_unannotated_python_executes(hugo_blog_factory):
    blog_root = hugo_blog_factory()
    os.chdir(blog_root)
    
    result = runner.invoke(app, ["check", "--post", "flat-post"])
    assert result.exit_code == 0
    assert "passed=2" in result.stdout
