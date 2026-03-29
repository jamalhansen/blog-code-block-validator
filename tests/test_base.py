import pytest
import duckdb
from blog_validate.languages.base import (
    AnnotationType, CodeBlock, ExecutionContext, ValidationError, Validator,
)


def test_annotation_type_string_values():
    assert AnnotationType.DEFAULT == "default"
    assert AnnotationType.SKIP == "skip"
    assert AnnotationType.EXPECTED_FAILURE == "expected-failure"
    assert AnnotationType.SYNTAX_ONLY == "syntax-only"
    assert AnnotationType.ASSERT == "assert"
    assert AnnotationType.FIXTURE == "fixture"
    assert AnnotationType.USE == "use"


def test_code_block_has_defaults():
    block = CodeBlock(language="python", code="x = 1", annotation=AnnotationType.DEFAULT)
    assert block.fixture_name is None
    assert block.post_slug == ""
    assert block.block_index == 0


def test_execution_context_has_empty_globals_by_default():
    conn = duckdb.connect(":memory:")
    ctx = ExecutionContext(conn=conn)
    assert ctx.py_globals == {}


def test_validation_error_is_exception():
    err = ValidationError("bad code")
    assert isinstance(err, Exception)
    assert str(err) == "bad code"


def test_validator_cannot_be_instantiated():
    with pytest.raises(TypeError):
        Validator()
