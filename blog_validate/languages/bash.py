import subprocess
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class BashValidator(Validator):
    language = "bash"

    def syntax_check(self, code: str) -> None:
        # Basic syntax check using 'bash -n'
        result = subprocess.run(
            ["bash", "-n"], input=code, capture_output=True, text=True
        )
        if result.returncode != 0:
            raise ValidationError(f"Bash syntax error: {result.stderr}")

    def execute(self, code: str, context: ExecutionContext) -> None:
        # Runs in the isolated temp dir provided by the runner
        try:
            subprocess.run(
                code, shell=True, capture_output=True, text=True, check=True
            )
        except subprocess.CalledProcessError as e:
            raise ValidationError(
                f"Bash command failed with exit code {e.returncode}: {e.stderr or e.stdout}"
            ) from e
        except Exception as e:
            raise ValidationError(f"Bash execution error: {e}") from e
