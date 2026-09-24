import os
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
        if not context.bash_execute:
            self.syntax_check(code)
            return
        # Runs in the isolated temp dir provided by the runner. HOME points
        # there too: the cwd alone doesn't stop `mkdir ~/bin` or `>> ~/.zshrc`
        # from reaching the real home directory.
        env = {**os.environ, "HOME": os.getcwd()}
        try:
            subprocess.run(
                code, shell=True, capture_output=True, text=True, check=True, env=env
            )
        except subprocess.CalledProcessError as e:
            output = e.stderr or e.stdout
            # POSIX shells report 127 for "command not found" -- distinct from a
            # command that ran and failed. This is almost always a machine-
            # specific tool (brew, a locally-installed CLI) that will never be
            # present in every environment the validator runs in, so the fix is
            # usually test:skip, not a real bug in the post.
            if e.returncode == 127:
                raise ValidationError(
                    f"Command not found (exit 127): {output.strip()}\n"
                    "This usually means a machine-specific tool isn't installed "
                    "in the validator's environment. If this command only needs "
                    "to work on your own machine, mark the block "
                    "<!-- test:skip --> instead of expecting it to run everywhere."
                ) from e
            raise ValidationError(
                f"Bash command failed with exit code {e.returncode}: {output}"
            ) from e
        except Exception as e:
            raise ValidationError(f"Bash execution error: {e}") from e
