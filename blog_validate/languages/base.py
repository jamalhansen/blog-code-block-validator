from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AnnotationType(str, Enum):
    DEFAULT = "default"
    SKIP = "skip"
    EXPECTED_FAILURE = "expected-failure"
    SETUP = "setup"
    SYNTAX_ONLY = "syntax-only"
    ASSERT = "assert"
    FIXTURE = "fixture"
    USE = "use"


@dataclass
class CodeBlock:
    language: str
    code: str
    annotation: AnnotationType
    fixture_name: str | None = None
    post_slug: str = ""
    block_index: int = 0


@dataclass
class ExecutionContext:
    conn: Any  # duckdb.DuckDBPyConnection
    py_globals: dict = field(default_factory=dict)
    last_stdout: str | None = None  # set by validators that capture stdout (e.g. python)
    bash_execute: bool = True  # False = bash blocks are syntax-checked only ([bash] execute)


class ValidationError(Exception):
    def __init__(
        self,
        message: str,
        detail: str | None = None,
        stdout: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail  # e.g. "Left: X\nRight: Y" for assertion failures
        self.stdout = stdout  # captured stdout from exec, if any

    def __str__(self) -> str:
        return self.message


class Validator(ABC):
    language: str

    @abstractmethod
    def syntax_check(self, code: str) -> None:
        """Check syntax only. Raise ValidationError if invalid."""

    @abstractmethod
    def execute(self, code: str, context: ExecutionContext) -> None:
        """Execute code in context. Raise ValidationError on failure."""
