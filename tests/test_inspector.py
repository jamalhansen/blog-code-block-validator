from blog_validate.inspector import (
    _has_assert_statements,
    _count_ollama_calls,
    _detect_imports,
    _has_file_reads,
    _has_open_mock,
    _extract_sql_tables,
    analyze_post,
    format_guide,
    PostInsight,
    BlockInsight,
)
from blog_validate.extractor import PostBlocks
from blog_validate.languages.base import AnnotationType, CodeBlock


def _block(code: str, language: str = "python", annotation: AnnotationType = AnnotationType.DEFAULT, index: int = 0) -> CodeBlock:
    return CodeBlock(
        code=code,
        language=language,
        block_index=index,
        annotation=annotation,
    )


def _post(slug: str, blocks: list[CodeBlock], needs: list[tuple[str, str | None]] | None = None) -> PostBlocks:
    return PostBlocks(slug=slug, blocks=blocks, needs=needs or [])


class TestHasAssertStatements:
    def test_returns_true_for_assert(self):
        assert _has_assert_statements("assert x == 1") is True

    def test_returns_false_for_no_assert(self):
        assert _has_assert_statements("x = 1\nprint(x)") is False

    def test_handles_syntax_error(self):
        assert _has_assert_statements("def (broken") is False

    def test_assert_in_function(self):
        code = "def check():\n    assert result == 'ok'"
        assert _has_assert_statements(code) is True


class TestCountOllamaCalls:
    def test_single_call(self):
        code = 'response = ollama.chat(model="llama3", messages=[])'
        assert _count_ollama_calls(code) == 1

    def test_multiple_calls(self):
        code = 'r1 = ollama.chat(model="x", messages=[])\nr2 = ollama.chat(model="x", messages=[])'
        assert _count_ollama_calls(code) == 2

    def test_no_calls(self):
        assert _count_ollama_calls("x = 1") == 0

    def test_other_chat_method_not_counted(self):
        assert _count_ollama_calls("client.chat(messages=[])") == 0

    def test_handles_syntax_error(self):
        assert _count_ollama_calls("def (broken") == 0


class TestDetectImports:
    def test_simple_import(self):
        assert "os" in _detect_imports("import os")

    def test_from_import(self):
        assert "pathlib" in _detect_imports("from pathlib import Path")

    def test_multiple_imports(self):
        result = _detect_imports("import os\nimport sys")
        assert "os" in result
        assert "sys" in result

    def test_deduplicates(self):
        result = _detect_imports("import os\nimport os")
        assert result.count("os") == 1

    def test_handles_syntax_error(self):
        assert _detect_imports("def (broken") == []

    def test_submodule_returns_top_level(self):
        assert "os" in _detect_imports("import os.path")


class TestHasFileReads:
    def test_detects_open_call(self):
        assert _has_file_reads('f = open("file.txt")') is True

    def test_no_open_call(self):
        assert _has_file_reads("x = 1") is False

    def test_handles_syntax_error(self):
        assert _has_file_reads("def (broken") is False


class TestHasOpenMock:
    def test_detects_magic_mock(self):
        assert _has_open_mock("m = MagicMock()") is True

    def test_detects_mock_open(self):
        assert _has_open_mock("mock_open(read_data='hello')") is True

    def test_detects_builtins_open(self):
        assert _has_open_mock("builtins.open = lambda f: None") is True

    def test_detects_unittest_mock(self):
        assert _has_open_mock("from unittest.mock import patch") is True

    def test_no_mock(self):
        assert _has_open_mock("x = 1") is False


class TestExtractSqlTables:
    def test_from_clause(self):
        assert "users" in _extract_sql_tables("SELECT * FROM users")

    def test_join_clause(self):
        assert "orders" in _extract_sql_tables("SELECT * FROM users JOIN orders ON users.id = orders.user_id")

    def test_create_table(self):
        assert "products" in _extract_sql_tables("CREATE TABLE products (id INT)")

    def test_create_table_if_not_exists(self):
        assert "products" in _extract_sql_tables("CREATE TABLE IF NOT EXISTS products (id INT)")

    def test_insert_into(self):
        assert "events" in _extract_sql_tables("INSERT INTO events VALUES (1)")

    def test_deduplicates(self):
        result = _extract_sql_tables("SELECT * FROM users JOIN users ON users.id = users.manager_id")
        assert result.count("users") == 1

    def test_excludes_keywords(self):
        result = _extract_sql_tables("SELECT * FROM (SELECT 1) sub")
        assert "SELECT" not in result


class TestAnalyzePost:
    def test_python_block_detects_ollama(self):
        blocks = [_block('ollama.chat(model="x", messages=[])')]
        post = _post("my-post", blocks, needs=[("ollama_mock", "response1")])
        insight = analyze_post(post)
        assert insight.total_ollama_calls == 1
        assert insight.ollama_mocked is True

    def test_sql_block_extracts_tables(self):
        blocks = [_block("SELECT * FROM orders", language="sql", annotation=AnnotationType.DEFAULT)]
        post = _post("sql-post", blocks)
        insight = analyze_post(post)
        assert "orders" in insight.all_tables

    def test_needs_params_parsed(self):
        post = _post("p", [], needs=[("ollama_mock", "r1|r2")])
        insight = analyze_post(post)
        assert insight.mock_response_count == 2

    def test_has_setup_block(self):
        blocks = [_block("x = 1", annotation=AnnotationType.SETUP)]
        post = _post("p", blocks)
        insight = analyze_post(post)
        assert insight.has_setup_blocks is True

    def test_has_assert_block(self):
        blocks = [_block("assert x == 1", annotation=AnnotationType.ASSERT)]
        post = _post("p", blocks)
        insight = analyze_post(post)
        assert insight.has_assert_blocks is True

    def test_has_assert_statement_in_default_block(self):
        blocks = [_block("assert x == 1")]
        post = _post("p", blocks)
        insight = analyze_post(post)
        assert insight.has_assert_blocks is True

    def test_file_reads_detected(self):
        blocks = [_block('f = open("data.csv")')]
        post = _post("p", blocks)
        insight = analyze_post(post)
        assert any(b.has_file_reads for b in insight.python_blocks)

    def test_non_python_block_ignored_for_ollama(self):
        blocks = [_block("SELECT 1", language="sql")]
        post = _post("p", blocks)
        insight = analyze_post(post)
        assert insight.total_ollama_calls == 0


class TestPostInsightProperties:
    def _make_insight(self, blocks: list[BlockInsight], needs: dict | None = None) -> PostInsight:
        return PostInsight(slug="test", blocks=blocks, needs_params=needs or {})

    def test_python_blocks_filtered(self):
        blocks = [
            BlockInsight(language="python", block_index=0, annotation=AnnotationType.DEFAULT),
            BlockInsight(language="sql", block_index=1, annotation=AnnotationType.DEFAULT),
        ]
        insight = self._make_insight(blocks)
        assert len(insight.python_blocks) == 1
        assert len(insight.sql_blocks) == 1

    def test_mock_response_count_with_pipe(self):
        insight = self._make_insight([], needs={"ollama_mock": "r1|r2|r3"})
        assert insight.mock_response_count == 3

    def test_mock_response_count_no_mock(self):
        insight = self._make_insight([])
        assert insight.mock_response_count == 0

    def test_unannotated_count(self):
        blocks = [
            BlockInsight(language="python", block_index=0, annotation=AnnotationType.DEFAULT),
            BlockInsight(language="python", block_index=1, annotation=AnnotationType.SETUP),
        ]
        insight = self._make_insight(blocks)
        assert insight.unannotated_count == 1

    def test_has_create_table_from_setup_sql(self):
        blocks = [
            BlockInsight(language="sql", block_index=0, annotation=AnnotationType.SETUP),
        ]
        insight = self._make_insight(blocks)
        assert insight.has_create_table is True

    def test_all_tables_deduplicates(self):
        blocks = [
            BlockInsight(language="sql", block_index=0, annotation=AnnotationType.DEFAULT, sql_tables=["users"]),
            BlockInsight(language="sql", block_index=1, annotation=AnnotationType.DEFAULT, sql_tables=["users", "orders"]),
        ]
        insight = self._make_insight(blocks)
        assert insight.all_tables.count("users") == 1
        assert "orders" in insight.all_tables


class TestFormatGuide:
    def _python_post(self, code: str, annotation: AnnotationType = AnnotationType.DEFAULT, needs: list | None = None) -> PostBlocks:
        return _post("test-post", [_block(code, annotation=annotation)], needs=needs or [])

    def test_includes_slug(self):
        post = _post("my-post", [_block("x = 1")])
        guide = format_guide(analyze_post(post))
        assert "my-post" in guide

    def test_ollama_not_mocked_shows_fix(self):
        code = 'ollama.chat(model="x", messages=[])'
        post = self._python_post(code)
        guide = format_guide(analyze_post(post))
        assert "ollama_mock" in guide
        assert "Fix" in guide

    def test_ollama_mocked_with_enough_responses(self):
        code = 'ollama.chat(model="x", messages=[])'
        post = self._python_post(code, needs=[("ollama_mock", "response1")])
        guide = format_guide(analyze_post(post))
        assert "1 response(s) configured" in guide

    def test_ollama_mocked_too_few_responses(self):
        code = 'r1 = ollama.chat(model="x", messages=[])\nr2 = ollama.chat(model="x", messages=[])'
        post = self._python_post(code, needs=[("ollama_mock", "r1")])
        guide = format_guide(analyze_post(post))
        assert "only 1 response(s)" in guide

    def test_sql_no_data_shows_fix(self):
        blocks = [_block("SELECT * FROM orders", language="sql")]
        post = _post("sql-post", blocks)
        guide = format_guide(analyze_post(post))
        assert "DuckDB starts empty" in guide
        assert "orders" in guide

    def test_sql_with_setup_shows_pass(self):
        blocks = [
            _block("CREATE TABLE orders (id INT)", language="sql", annotation=AnnotationType.SETUP),
            _block("SELECT * FROM orders", language="sql"),
        ]
        post = _post("sql-post", blocks)
        guide = format_guide(analyze_post(post))
        assert "setup/CREATE TABLE present" in guide

    def test_assert_present_shows_check(self):
        post = self._python_post("assert x == 1")
        guide = format_guide(analyze_post(post))
        assert "assert block(s) present" in guide

    def test_no_assert_shows_warning(self):
        post = self._python_post("x = 1 + 1")
        guide = format_guide(analyze_post(post))
        assert "unannotated block(s) with no assertions" in guide

    def test_file_io_without_mock_shows_fix(self):
        post = self._python_post('f = open("data.csv")')
        guide = format_guide(analyze_post(post))
        assert "open() calls detected" in guide
        assert "no setup block" in guide

    def test_file_io_with_mock_shows_pass(self):
        code = 'f = open("data.csv")\nm = MagicMock()'
        post = self._python_post(code)
        guide = format_guide(analyze_post(post))
        assert "appears to be mocked" in guide
