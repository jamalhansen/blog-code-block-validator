import pytest
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


def test_load_config_invalid_layout_raises(tmp_path):
    (tmp_path / "blog-validate.toml").write_text('[blog]\nlayout = "typo"\n')
    with pytest.raises(ValueError, match="Invalid layout"):
        load_config(tmp_path)


def test_load_config_valid_layouts(tmp_path):
    for layout in ("bundle", "flat", "vault"):
        (tmp_path / "blog-validate.toml").write_text(f'[blog]\nlayout = "{layout}"\n')
        config = load_config(tmp_path)
        assert config.blog.layout == layout


def test_load_config_python_venv_defaults_to_none(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    assert load_config(tmp_path).python.venv is None


def test_load_config_bash_and_status_defaults(tmp_path):
    (tmp_path / "blog-validate.toml").write_text("")
    config = load_config(tmp_path)
    assert config.bash.execute is True
    assert config.blog.skip_statuses == []


def test_load_config_reads_bash_and_skip_statuses(tmp_path):
    (tmp_path / "blog-validate.toml").write_text(
        '[blog]\nskip_statuses = ["dropped"]\n[bash]\nexecute = false\n'
    )
    config = load_config(tmp_path)
    assert config.bash.execute is False
    assert config.blog.skip_statuses == ["dropped"]


def test_load_config_reads_python_venv(tmp_path):
    (tmp_path / "blog-validate.toml").write_text('[python]\nvenv = "~/projects/blog/.venv"\n')
    assert load_config(tmp_path).python.venv == "~/projects/blog/.venv"
