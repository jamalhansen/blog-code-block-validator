import ast
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class PythonValidator(Validator):
    language = "python"

    def syntax_check(self, code: str) -> None:
        try:
            ast.parse(code)
        except SyntaxError as e:
            raise ValidationError(f"Python syntax error: {e}") from e

    def execute(self, code: str, context: ExecutionContext) -> None:
        try:
            exec(compile(code, "<blog>", "exec"), context.py_globals)
        except AssertionError as e:
            raise ValidationError(f"Assertion failed: {e}") from e
        except Exception as e:
            raise ValidationError(
                f"Python execution error: {type(e).__name__}: {e}"
            ) from e
