import pytest
from pathlib import Path
from blog_validate.config import load_config


def test_load_config_finds_toml_in_current_dir(tmp_path):
    (tmp_path / "blog-validate.toml").write_text(
        '[blog]\ncontent_path = "content/posts"\n'
    )
    config = load_config(tmp_path)
    assert config.blog.content_path == "content/posts"
    assert config.root == tmp_path


def test_load_config_walks_up_to_parent(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    subdir = tmp_path / "content" / "blog" / "my-post"
    subdir.mkdir(parents=True)
    config = load_config(subdir)
    assert config.root == tmp_path


def test_load_config_uses_defaults_for_missing_keys(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    config = load_config(tmp_path)
    assert config.blog.content_path == "content/blog"
    assert config.blog.post_file == "index.md"
    assert config.sql.backend == "duckdb"


def test_load_config_raises_if_not_found(tmp_path):
    isolated = tmp_path / "deep" / "nested"
    isolated.mkdir(parents=True)
    with pytest.raises(FileNotFoundError, match="blog-validate.toml not found"):
        load_config(isolated)
