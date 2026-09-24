import pytest
from blog_validate.languages.bash import BashValidator
from blog_validate.languages.markdown import MarkdownValidator
from blog_validate.languages.toml import TomlValidator
from blog_validate.languages.base import ExecutionContext, ValidationError


@pytest.fixture
def ctx():
    import duckdb
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={})


class TestBashValidator:
    def test_execute_passes_on_success(self, ctx):
        v = BashValidator()
        v.execute("echo hello", ctx)  # should not raise

    def test_home_is_the_isolated_cwd_not_the_real_home(self, ctx, tmp_path, monkeypatch):
        """`mkdir ~/bin` in a post must land in the throwaway dir, never the author's home."""
        real_home = tmp_path / "real-home"
        real_home.mkdir()
        sandbox = tmp_path / "sandbox"
        sandbox.mkdir()
        monkeypatch.setenv("HOME", str(real_home))
        monkeypatch.chdir(sandbox)
        BashValidator().execute("mkdir ~/bin", ctx)
        assert (sandbox / "bin").is_dir()
        assert not (real_home / "bin").exists()

    def test_execute_false_only_checks_syntax(self, ctx, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        ctx.bash_execute = False
        v = BashValidator()
        v.execute("touch should-not-exist && exit 1", ctx)  # valid syntax: passes, never runs
        assert not (tmp_path / "should-not-exist").exists()
        with pytest.raises(ValidationError, match="syntax error"):
            v.execute("if then fi (", ctx)

    def test_execute_raises_on_failure(self, ctx):
        v = BashValidator()
        with pytest.raises(ValidationError, match="exit code"):
            v.execute("exit 1", ctx)

    def test_syntax_check_valid(self, ctx):
        v = BashValidator()
        v.syntax_check("echo hello")  # should not raise

    def test_syntax_check_invalid(self, ctx):
        v = BashValidator()
        with pytest.raises(ValidationError, match="syntax error"):
            v.syntax_check("if [ then")

    def test_command_not_found_reports_exit_127_distinctly(self, ctx):
        v = BashValidator()
        with pytest.raises(ValidationError, match="Command not found \\(exit 127\\)"):
            v.execute("this-command-definitely-does-not-exist-anywhere", ctx)

    def test_command_not_found_suggests_test_skip(self, ctx):
        v = BashValidator()
        with pytest.raises(ValidationError, match="test:skip"):
            v.execute("this-command-definitely-does-not-exist-anywhere", ctx)

    def test_generic_failure_does_not_mention_command_not_found(self, ctx):
        v = BashValidator()
        with pytest.raises(ValidationError) as exc_info:
            v.execute("exit 1", ctx)
        assert "Command not found" not in str(exc_info.value)


class TestMarkdownValidator:
    def test_execute_passes_on_valid_markdown(self, ctx):
        v = MarkdownValidator()
        v.execute("# Hello\n\nSome paragraph text.\n", ctx)

    def test_execute_raises_on_lint_errors(self, ctx):
        v = MarkdownValidator()
        # MD010: hard tabs are a lint error
        with pytest.raises(ValidationError):
            v.execute("# Title\n\n\t- item with hard tab\n", ctx)

    def test_syntax_check_delegates_to_execute(self, ctx):
        v = MarkdownValidator()
        v.syntax_check("# Valid Markdown\n\nParagraph.\n")  # should not raise


class TestTomlValidator:
    def test_execute_passes_on_valid_toml(self, ctx):
        v = TomlValidator()
        v.execute('[server]\nhost = "localhost"\nport = 8080\n', ctx)

    def test_execute_raises_on_invalid_toml(self, ctx):
        v = TomlValidator()
        with pytest.raises(ValidationError, match="TOML syntax error"):
            v.execute("key = [unclosed", ctx)

    def test_syntax_check_valid(self, ctx):
        v = TomlValidator()
        v.syntax_check('name = "test"')

    def test_syntax_check_invalid(self, ctx):
        v = TomlValidator()
        with pytest.raises(ValidationError, match="TOML syntax error"):
            v.syntax_check("key = [unclosed")
