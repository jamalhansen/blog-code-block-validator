import hashlib
import re

import duckdb
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


MAX_FINGERPRINT_ROWS = 10_000


def result_fingerprint(cursor) -> dict | None:
    """Columns, row count and a digest of the rows a query returned; None for statements."""
    if not cursor.description:
        return None
    rows = cursor.fetchmany(MAX_FINGERPRINT_ROWS + 1)
    return {
        "columns": [d[0] for d in cursor.description],
        "rows": len(rows),
        # Order-insensitive: without ORDER BY (or with ties) DuckDB may return rows in any order.
        "digest": hashlib.sha256(repr(sorted(map(repr, rows))).encode()).hexdigest()[:16],
    }


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
            context.last_result = None
            cursor = context.conn.execute(code)
            # EXPLAIN output carries timings and version-specific plans: never snapshot it.
            if not re.match(r"\s*(--[^\n]*\n\s*)*EXPLAIN\b", code, re.I):
                context.last_result = result_fingerprint(cursor)
        except Exception as e:
            raise ValidationError(
                f"SQL execution error: {type(e).__name__}: {e}"
            ) from e

    def execute_assert(self, code: str, context: ExecutionContext) -> None:
        """Execute as assertion. Query must return a single truthy value."""
        try:
            result = context.conn.execute(code).fetchone()
        except Exception as e:
            raise ValidationError(
                f"SQL assertion error: {type(e).__name__}: {e}"
            ) from e

        if result is None:
            raise ValidationError("SQL assertion returned no rows")

        if not result[0]:
            raise ValidationError(
                f"SQL assertion failed: expected truthy, got {result[0]!r}"
            )
