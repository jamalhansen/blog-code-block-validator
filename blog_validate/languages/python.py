import ast
import io
import contextlib
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


def _introspect_assertion(code: str, py_globals: dict) -> str | None:
    """Extract left/right values from a failing assert for display."""
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Assert):
                test = node.test
                if isinstance(test, ast.Compare) and len(test.ops) == 1:
                    left_src = ast.unparse(test.left)
                    right_src = ast.unparse(test.comparators[0])
                    try:
                        left_repr = repr(eval(left_src, py_globals))  # noqa: S307
                    except Exception:
                        left_repr = f"<could not evaluate {left_src!r}>"
                    try:
                        right_repr = repr(eval(right_src, py_globals))  # noqa: S307
                    except Exception:
                        right_repr = f"<could not evaluate {right_src!r}>"
                    return f"  Left:  {left_repr}\n  Right: {right_repr}"
    except Exception:
        pass
    return None


class PythonValidator(Validator):
    language = "python"

    def syntax_check(self, code: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValidationError(f"Python syntax error: {e}") from e

    def execute(self, code: str, context: ExecutionContext) -> None:
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
            try:
                exec(compile(code, "<blog>", "exec"), context.py_globals)
                context.last_stdout = stdout_buf.getvalue() or None
            except AssertionError as e:
                detail = _introspect_assertion(code, context.py_globals)
                stdout = stdout_buf.getvalue()
                raise ValidationError(
                    f"Assertion failed: {e}",
                    detail=detail,
                    stdout=stdout if stdout.strip() else None,
                ) from e
            except Exception as e:
                stdout = stdout_buf.getvalue()
                raise ValidationError(
                    f"Python execution error: {type(e).__name__}: {e}",
                    stdout=stdout if stdout.strip() else None,
                ) from e
