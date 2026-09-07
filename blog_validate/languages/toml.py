import tomllib
from blog_validate.languages.base import ExecutionContext, ValidationError, Validator


class TomlValidator(Validator):
    language = "toml"

    def syntax_check(self, code: str) -> None:
        try:
            tomllib.loads(code)
        except tomllib.TOMLDecodeError as e:
            raise ValidationError(f"TOML syntax error: {e}") from e

    def execute(self, code: str, context: ExecutionContext) -> None:
        # For TOML, execution just means syntax validation
        self.syntax_check(code)
