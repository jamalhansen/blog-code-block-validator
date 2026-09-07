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
