import duckdb
import pytest
from blog_validate.languages.base import ExecutionContext, ValidationError
from blog_validate.languages.sql import SQLValidator


@pytest.fixture
def conn():
    c = duckdb.connect(":memory:")
    yield c
    c.close()


@pytest.fixture
def ctx(conn):
    return ExecutionContext(conn=conn, py_globals={})


@pytest.fixture
def validator():
    return SQLValidator()


class TestSQLSyntaxCheck:
    def test_valid_select_passes(self, validator):
        validator.syntax_check("SELECT 1")

    def test_syntax_error_raises_validation_error(self, validator):
        with pytest.raises(ValidationError, match="SQL syntax error"):
            validator.syntax_check("SELECT FROM WHERE")

    def test_missing_table_is_not_a_syntax_error(self, validator):
        validator.syntax_check("SELECT * FROM nonexistent_table")


class TestSQLExecute:
    def test_select_executes(self, validator, ctx):
        validator.execute("SELECT 42", ctx)

    def test_create_table_executes(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT)", ctx)

    def test_schema_persists_across_calls(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT)", ctx)
        validator.execute("INSERT INTO t VALUES (1)", ctx)
        validator.execute("SELECT * FROM t", ctx)

    def test_error_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL execution error"):
            validator.execute("SELECT * FROM nonexistent_table", ctx)


class TestSQLExecuteAssert:
    def test_truthy_result_passes(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT); INSERT INTO t VALUES (1),(2)", ctx)
        validator.execute_assert("SELECT COUNT(*) = 2 FROM t", ctx)

    def test_false_result_raises(self, validator, ctx):
        validator.execute("CREATE TABLE t (id INT); INSERT INTO t VALUES (1)", ctx)
        with pytest.raises(ValidationError, match="SQL assertion failed"):
            validator.execute_assert("SELECT COUNT(*) = 99 FROM t", ctx)

    def test_no_rows_raises(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL assertion returned no rows"):
            validator.execute_assert("SELECT 1 WHERE 1=0", ctx)

    def test_error_in_assert_raises_validation_error(self, validator, ctx):
        with pytest.raises(ValidationError, match="SQL assertion error"):
            validator.execute_assert("SELECT * FROM nonexistent", ctx)
