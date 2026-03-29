import duckdb
from blog_validate.languages.base import ExecutionContext, Validator
from blog_validate.languages.python import PythonValidator
from blog_validate.languages.sql import SQLValidator

VALIDATORS: dict[str, Validator] = {
    "python": PythonValidator(),
    "sql": SQLValidator(),
}


def make_context() -> ExecutionContext:
    """Create a fresh execution context for a post."""
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={"conn": conn})
