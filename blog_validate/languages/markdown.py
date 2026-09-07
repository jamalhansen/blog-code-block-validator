import subprocess
import sys
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class MarkdownValidator(Validator):
    language = "markdown"

    def syntax_check(self, code: str) -> None:
        # Markdown doesn't really have "syntax" errors, so we lint it
        self.execute(code, ExecutionContext(conn=None, py_globals={}))

    def execute(self, code: str, context: ExecutionContext) -> None:
        # Use pymarkdown scan-stdin for linting
        try:
            # We disable some noisy rules by default (MD013 line length, MD041 first line header)
            # since these are snippets, not full documents.
            result = subprocess.run(
                [sys.executable, "-m", "pymarkdown", "-d", "MD013,MD041,MD047", "scan-stdin"],
                input=code,
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                # pymarkdown return code is non-zero if lint errors are found
                raise ValidationError(f"Markdown linting errors:\n{result.stdout or result.stderr}")
        except Exception as e:
            raise ValidationError(f"Markdown linting error: {e}") from e
