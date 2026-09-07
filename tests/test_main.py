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


class TestTestGuideCommand:
    def test_requires_post_or_all(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["test-guide"])
        assert result.exit_code == 1
        assert "--post" in result.output or "--all" in result.output

    def test_unknown_post_exits_1(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["test-guide", "--post", "nonexistent"])
        assert result.exit_code == 1

    def test_shows_guide_for_single_post(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["test-guide", "--post", "my-post"])
        assert result.exit_code == 0
        assert "test-guide: my-post" in result.output
        assert "Assertions" in result.output

    def test_all_posts_prints_each_guide(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        for slug in ("post-a", "post-b"):
            post_dir = tmp_path / "content" / "blog" / slug
            post_dir.mkdir(parents=True)
            (post_dir / "index.md").write_text("```sql\nSELECT 1\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["test-guide", "--all"])
        assert result.exit_code == 0
        assert "test-guide: post-a" in result.output
        assert "test-guide: post-b" in result.output

    def test_all_posts_skips_posts_with_no_blocks(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "prose-only"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("Just prose, no code.\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["test-guide", "--all"])
        assert result.exit_code == 0
        assert "prose-only" not in result.output

    def test_ollama_block_flags_missing_mock(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "ollama-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            "```python\nimport ollama\nollama.chat(model='x')\n```\n"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["test-guide", "--post", "ollama-post"])
        assert result.exit_code == 0
        assert "ollama_mock not loaded" in result.output


class TestStatsCommand:
    def test_no_blocks_reports_none_found(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "prose-only"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("Just prose.\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "No code blocks found" in result.output

    def test_reports_language_distribution(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "sql" in result.output
        assert "Total: 1 blocks across 1 posts" in result.output

    def test_multiple_languages_all_counted(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "mixed"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text(
            "```sql\nSELECT 1\n```\n```python\nx = 1\n```\n```python\ny = 2\n```\n"
        )
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Total: 3 blocks across 1 posts" in result.output


class TestFindCommand:
    def test_finds_posts_with_matching_language(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["find", "sql"])
        assert result.exit_code == 0
        assert "my-post" in result.output
        assert "Total: 1 posts, 1 blocks" in result.output

    def test_case_insensitive_match(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["find", "SQL"])
        assert result.exit_code == 0
        assert "my-post" in result.output

    def test_no_matches_reports_none_found(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["find", "rust"])
        assert result.exit_code == 0
        assert "No posts found" in result.output

    def test_count_flag_shows_per_post_counts(self, tmp_path, monkeypatch):
        (tmp_path / "blog-validate.toml").write_text(
            '[blog]\ncontent_path = "content/blog"\npost_file = "index.md"\n'
        )
        post_dir = tmp_path / "content" / "blog" / "two-blocks"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```python\nx = 1\n```\n```python\ny = 2\n```\n")
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["find", "python"])
        assert result.exit_code == 0
        assert "2 blocks" in result.output

    def test_no_count_flag_hides_counts(self, blog_root, monkeypatch):
        monkeypatch.chdir(blog_root)
        result = runner.invoke(app, ["find", "sql", "--no-count"])
        assert result.exit_code == 0
        # Per-post line should be the bare slug, not "slug  N block(s)"
        lines = [line for line in result.output.splitlines() if "my-post" in line]
        assert lines == ["  my-post"]


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
