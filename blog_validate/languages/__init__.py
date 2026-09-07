import duckdb
from blog_validate.languages.base import ExecutionContext, Validator
from blog_validate.languages.python import PythonValidator
from blog_validate.languages.sql import SQLValidator
from blog_validate.languages.bash import BashValidator
from blog_validate.languages.toml import TomlValidator
from blog_validate.languages.markdown import MarkdownValidator

VALIDATORS: dict[str, Validator] = {
    "python": PythonValidator(),
    "sql": SQLValidator(),
    "bash": BashValidator(),
    "sh": BashValidator(),
    "toml": TomlValidator(),
    "markdown": MarkdownValidator(),
    "md": MarkdownValidator(),
}


def make_context() -> ExecutionContext:
    """Create a fresh execution context for a post."""
    conn = duckdb.connect(":memory:")
    return ExecutionContext(conn=conn, py_globals={"conn": conn, "con": conn})
