import duckdb
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class SQLValidator(Validator):
    language = "sql"

    def syntax_check(self, code: str) -> None:
        """Check SQL syntax using EXPLAIN against a fresh connection.

        Only raises ValidationError for Parser Errors. Semantic errors
        (missing tables, wrong types) are not syntax errors and are ignored.
        """
        try:
            conn = duckdb.connect(":memory:")
            conn.execute(f"EXPLAIN {code}")
            conn.close()
        except duckdb.Error as e:
            err = str(e)
            if "Parser Error" in err or "parser error" in err.lower():
                raise ValidationError(f"SQL syntax error: {e}") from e
            # Other errors (missing tables, etc.) are semantic, not syntax

    def execute(self, code: str, context: ExecutionContext) -> None:
        try:
            context.conn.execute(code)
        except Exception as e:
            raise ValidationError(f"SQL execution error: {type(e).__name__}: {e}") from e

    def execute_assert(self, code: str, context: ExecutionContext) -> None:
        """Execute as assertion. Query must return a single truthy value."""
        try:
            result = context.conn.execute(code).fetchone()
        except Exception as e:
            raise ValidationError(f"SQL assertion error: {type(e).__name__}: {e}") from e

        if result is None:
            raise ValidationError("SQL assertion returned no rows")

        if not result[0]:
            raise ValidationError(
                f"SQL assertion failed: expected truthy, got {result[0]!r}"
            )
