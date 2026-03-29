import pytest
from typer.testing import CliRunner
from blog_validate.main import app, _code_preview

runner = CliRunner()


@pytest.fixture
def blog_root(tmp_path):
    (tmp_path / "blog-validate.toml").write_text(
        '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
    )
    post_dir = tmp_path / "content" / "blog" / "my-post"
    post_dir.mkdir(parents=True)
    (post_dir / "index.md").write_text("# My Post\n\n```sql\nSELECT 1\n```\n")
    return tmp_path


class TestCheckCommand:
    def test_check_all_passes_valid_blog(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all"])
        assert result.exit_code == 0
        assert "PASS" in result.output

    def test_check_post_by_slug_passes(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--post", "my-post"])
        assert result.exit_code == 0

    def test_check_unknown_slug_exits_1(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--post", "nonexistent"])
        assert result.exit_code == 1

    def test_check_with_no_mode_flag_exits_1(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check"])
        assert result.exit_code == 1

    def test_check_all_failing_post_exits_1(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "bad-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```sql\nSELECT * FROM nonexistent\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--all"])
        assert result.exit_code == 1
        assert "FAIL" in result.output

    def test_dry_run_always_exits_0(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "bad-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```sql\nSELECT * FROM nonexistent\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["check", "--all", "--dry-run"])
        assert result.exit_code == 0

    def test_verbose_shows_block_details(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all", "--verbose"])
        assert result.exit_code == 0
        assert "block" in result.output.lower()

    def test_summary_line_shows_counts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["check", "--all"])
        assert "Done." in result.output


class TestListCommands:
    def test_list_fixtures_with_no_fixtures(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-fixtures"])
        assert result.exit_code == 0
        assert "No named fixtures" in result.output

    def test_list_fixtures_shows_defined_fixtures(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "setup-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            '<!-- test:fixture name="users-table" -->\n```sql\nCREATE TABLE users (id INT);\n```\n'
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["list-fixtures"])
        assert result.exit_code == 0
        assert "users-table" in result.output
        assert "setup-post" in result.output

    def test_list_posts_shows_all_posts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-posts"])
        assert result.exit_code == 0
        assert "my-post" in result.output

    def test_list_posts_shows_block_counts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-posts"])
        assert "1 block" in result.output or "blocks" in result.output

    def test_list_skips_no_skips(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["list-skips"])
        assert result.exit_code == 0
        assert "Total: 0 skipped blocks" in result.output

    def test_list_skips_shows_skipped_blocks(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "skip-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            "<!-- test:skip -->\n```python\nimport requests\nrequests.get('http://example.com')\n```\n"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["list-skips"])
        assert result.exit_code == 0
        assert "skip-post" in result.output
        assert "block 0 (python)" in result.output
        assert "import requests" in result.output
        assert "Total: 1 skipped blocks" in result.output

    def test_list_skips_truncates_long_blocks(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "long-post"
        post_dir.mkdir(parents=True)
        code = "\n".join(f"line{i} = {i}" for i in range(10))
        (post_dir / "index.md").write_text(
            f"<!-- test:skip -->\n```python\n{code}\n```\n"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["list-skips"])
        assert "..." in result.output


class TestCheckChanged:
    def test_changed_with_no_staged_files(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)

        def fake_get_changed_files(root):
            return []

        monkeypatch.setattr(
            "blog_validate.main.get_changed_files", fake_get_changed_files
        )
        result = runner.invoke(app, ["check", "--changed"])
        assert result.exit_code == 0
        assert "No posts to validate" in result.output

    def test_changed_validates_staged_post(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        post_path = blog_root / "content" / "blog" / "my-post" / "index.md"

        def fake_get_changed_files(root):
            return [post_path]

        monkeypatch.setattr(
            "blog_validate.main.get_changed_files", fake_get_changed_files
        )
        result = runner.invoke(app, ["check", "--changed"])
        assert result.exit_code == 0
        assert "my-post" in result.output


class TestCodePreview:
    def test_short_block_no_ellipsis(self):
        code = "SELECT 1\nSELECT 2"
        result = _code_preview(code)
        assert "SELECT 1" in result
        assert "SELECT 2" in result
        assert "..." not in result

    def test_long_block_truncates_with_ellipsis(self):
        code = "\n".join(f"line {i}" for i in range(10))
        result = _code_preview(code)
        assert "line 0" in result
        assert "line 2" in result
        assert "line 3" not in result
        assert "..." in result

    def test_exactly_max_lines_no_ellipsis(self):
        code = "a\nb\nc"
        result = _code_preview(code)
        assert "..." not in result

    def test_lines_are_indented(self):
        result = _code_preview("SELECT 1")
        assert result.startswith("    ")
