import duckdb
import pytest
from blog_validate.languages.base import ExecutionContext, ValidationError
from blog_validate.languages.python import PythonValidator


@pytest.fixture
def ctx():
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={"conn": conn})


@pytest.fixture
def validator():
    return PythonValidator()


class TestPythonSyntaxCheck:
    def test_valid_syntax_passes(self, validator):
        validator.syntax_check("x = 1 + 2")

    def test_syntax_error_raises_validation_error(self, validator):
        with pytest.raises(ValidationError, match="Python syntax error"):
            validator.syntax_check("def foo(:\n    pass")

    def test_undefined_variable_is_valid_syntax(self, validator):
        validator.syntax_check("x = undefined_variable + 1")


class TestPythonExecute:
    def test_simple_assignment_executes(self, validator, ctx):
        validator.execute("x = 1 + 2", ctx)
        assert ctx.py_globals["x"] == 3

    def test_passing_assert_does_not_raise(self, validator, ctx):
        validator.execute("assert 1 == 1", ctx)

    def test_failing_assert_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="Assertion failed"):
            validator.execute("assert 1 == 2, 'not equal'", ctx)

    def test_runtime_exception_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="Python execution error"):
            validator.execute("raise RuntimeError('boom')", ctx)

    def test_globals_persist_across_calls(self, validator, ctx):
        validator.execute("x = 42", ctx)
        validator.execute("y = x + 1", ctx)
        assert ctx.py_globals["y"] == 43

    def test_conn_is_available_in_globals(self, validator, ctx):
        validator.execute("result = conn.execute('SELECT 42').fetchone()[0]", ctx)
        assert ctx.py_globals["result"] == 42
