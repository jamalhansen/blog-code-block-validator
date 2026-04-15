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
    assert "[PASS]" in result.stdout
