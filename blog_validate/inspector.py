"""Static analysis for test-guide: inspects code blocks without executing them."""
import ast
import re
from dataclasses import dataclass, field
from blog_validate.extractor import PostBlocks
from blog_validate.languages.base import AnnotationType


@dataclass
class BlockInsight:
    language: str
    block_index: int
    annotation: AnnotationType
    ollama_calls: int = 0
    imports: list[str] = field(default_factory=list)
    has_file_reads: bool = False
    sql_tables: list[str] = field(default_factory=list)
    has_assert_statements: bool = False
    has_open_mock: bool = False


@dataclass
class PostInsight:
    slug: str
    blocks: list[BlockInsight]
    needs_params: dict[str, str | None] = field(default_factory=dict)

    @property
    def python_blocks(self) -> list[BlockInsight]:
        return [b for b in self.blocks if b.language == "python"]

    @property
    def sql_blocks(self) -> list[BlockInsight]:
        return [b for b in self.blocks if b.language == "sql"]

    @property
    def total_ollama_calls(self) -> int:
        return sum(b.ollama_calls for b in self.python_blocks)

    @property
    def mock_response_count(self) -> int:
        param = self.needs_params.get("ollama_mock")
        if param is None:
            return 0
        return len(param.split("|"))

    @property
    def ollama_mocked(self) -> bool:
        return "ollama_mock" in self.needs_params

    @property
    def file_reads_mocked(self) -> bool:
        return any(b.has_open_mock for b in self.python_blocks)

    @property
    def has_assert_blocks(self) -> bool:
        return any(
            b.annotation == AnnotationType.ASSERT or b.has_assert_statements
            for b in self.blocks
        )

    @property
    def has_setup_blocks(self) -> bool:
        return any(b.annotation == AnnotationType.SETUP for b in self.blocks)

    @property
    def unannotated_count(self) -> int:
        return sum(1 for b in self.blocks if b.annotation == AnnotationType.DEFAULT)

    @property
    def all_tables(self) -> list[str]:
        tables = []
        for b in self.sql_blocks:
            tables.extend(b.sql_tables)
        return list(dict.fromkeys(tables))

    @property
    def has_create_table(self) -> bool:
        for b in self.sql_blocks:
            if b.annotation == AnnotationType.SETUP:
                return True
        return False


def _has_assert_statements(code: str) -> bool:
    try:
        tree = ast.parse(code)
        return any(isinstance(node, ast.Assert) for node in ast.walk(tree))
    except SyntaxError:
        return False


def _count_ollama_calls(code: str) -> int:
    try:
        tree = ast.parse(code)
        count = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Attribute) and func.attr == "chat":
                    if isinstance(func.value, ast.Name) and func.value.id == "ollama":
                        count += 1
        return count
    except SyntaxError:
        return 0


def _detect_imports(code: str) -> list[str]:
    try:
        tree = ast.parse(code)
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imports.append(node.module.split(".")[0])
        return list(dict.fromkeys(imports))
    except SyntaxError:
        return []


def _has_file_reads(code: str) -> bool:
    try:
        tree = ast.parse(code)
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                func = node.func
                if isinstance(func, ast.Name) and func.id == "open":
                    return True
        return False
    except SyntaxError:
        return False


def _has_open_mock(code: str) -> bool:
    """True if the code mocks open() (via MagicMock, mock_open, or builtins.open assignment)."""
    return (
        "MagicMock" in code
        or "mock_open" in code
        or "builtins.open" in code
        or "unittest.mock" in code
    )


def _extract_sql_tables(sql: str) -> list[str]:
    tables = []
    patterns = [
        r"\bFROM\s+(\w+)",
        r"\bJOIN\s+(\w+)",
        r"\bINTO\s+(\w+)",
        r"\bUPDATE\s+(\w+)",
        r"\bCREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?(\w+)",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, sql, re.IGNORECASE):
            name = m.group(1)
            if name.upper() not in ("SELECT", "VALUES", "SERIES"):
                tables.append(name)
    return list(dict.fromkeys(tables))


def analyze_post(post: PostBlocks) -> PostInsight:
    needs_params = {name: param for name, param in post.needs}

    block_insights = []
    for b in post.blocks:
        insight = BlockInsight(
            language=b.language,
            block_index=b.block_index,
            annotation=b.annotation,
        )
        if b.language == "python":
            insight.ollama_calls = _count_ollama_calls(b.code)
            insight.imports = _detect_imports(b.code)
            insight.has_file_reads = _has_file_reads(b.code)
            insight.has_assert_statements = _has_assert_statements(b.code)
            insight.has_open_mock = _has_open_mock(b.code)
        elif b.language == "sql":
            insight.sql_tables = _extract_sql_tables(b.code)
        block_insights.append(insight)

    return PostInsight(slug=post.slug, blocks=block_insights, needs_params=needs_params)


def format_guide(insight: PostInsight) -> str:
    lines = [
        f"test-guide: {insight.slug}",
        "─" * 50,
    ]

    py = insight.python_blocks
    sql = insight.sql_blocks
    lang_summary = []
    if py:
        annotations = {}
        for b in py:
            annotations[b.annotation.value] = annotations.get(b.annotation.value, 0) + 1
        ann_str = ", ".join(f"{k}={v}" for k, v in sorted(annotations.items()))
        lang_summary.append(f"{len(py)} python ({ann_str})")
    if sql:
        annotations = {}
        for b in sql:
            annotations[b.annotation.value] = annotations.get(b.annotation.value, 0) + 1
        ann_str = ", ".join(f"{k}={v}" for k, v in sorted(annotations.items()))
        lang_summary.append(f"{len(sql)} sql ({ann_str})")
    lines.append("Blocks:  " + "  ".join(lang_summary))
    lines.append("")

    if py and insight.total_ollama_calls > 0:
        lines.append("ollama")
        calls = insight.total_ollama_calls
        if insight.ollama_mocked:
            lines.append("  ✓ ollama_mock loaded")
            mocked = insight.mock_response_count
            if mocked == 0:
                lines.append(f"  ⚠ {calls} ollama.chat() call(s) detected, no custom responses (heuristic only)")
                lines.append(f"    Fix: <!-- test:needs: ollama_mock:response1{'|response2' if calls > 1 else ''} -->")
            elif mocked < calls:
                lines.append(f"  ⚠ {calls} ollama.chat() call(s), only {mocked} response(s) -- extra calls use heuristic")
                lines.append("    Note: if chat() is called in a loop, this count may be understated")
                param = insight.needs_params["ollama_mock"] or ""
                extras = "|".join(f"response{i}" for i in range(mocked + 1, calls + 1))
                lines.append(f"    Fix: <!-- test:needs: ollama_mock:{param}|{extras} -->")
            else:
                lines.append(f"  ✓ {mocked} response(s) configured for {calls} detected call(s)")
                if mocked > calls:
                    lines.append("    Note: chat() may be called in a loop -- extra responses are ready")
        else:
            lines.append("  ✗ ollama used but ollama_mock not loaded")
            lines.append(f"    Fix: <!-- test:needs: ollama_mock:response1{'|response2' if calls > 1 else ''} -->")
        lines.append("")

    if any(b.has_file_reads for b in py):
        lines.append("File I/O")
        lines.append("  ⚠ open() calls detected")
        if insight.file_reads_mocked:
            lines.append("  ✓ open() appears to be mocked")
        elif insight.has_setup_blocks:
            lines.append("  ✓ setup block present -- verify it creates needed files")
        else:
            lines.append("  ✗ no setup block -- use <!-- test:setup --> to create files, or mock open() with MagicMock")
        lines.append("")

    if sql:
        lines.append("Data")
        tables = insight.all_tables
        if tables:
            lines.append(f"  Tables referenced: {', '.join(tables)}")
        if insight.has_create_table or insight.has_setup_blocks:
            lines.append("  ✓ setup/CREATE TABLE present")
        else:
            lines.append("  ✗ no test data -- DuckDB starts empty")
            if tables:
                example = tables[0]
                lines.append("    Fix: add a <!-- test:setup --> block:")
                lines.append(f"      CREATE TABLE {example} AS")
                lines.append("      SELECT * FROM (VALUES (1, 'example')) t(id, name);")
        lines.append("")

    lines.append("Assertions")
    if insight.has_assert_blocks:
        lines.append("  ✓ assert block(s) present")
    else:
        unannotated = insight.unannotated_count
        if unannotated > 0:
            lines.append(f"  ✗ {unannotated} unannotated block(s) with no assertions")
            lines.append("    Fix: add <!-- test:assert:start --> / <!-- test:assert:end --> around a verification block")
        else:
            lines.append("  ⚠ no assert blocks found -- consider adding assertions")

    lines.append("")
    lines.append("Tips")
    if py and insight.total_ollama_calls > 0:
        lines.append("  • Pin exact mock responses to make assertions deterministic")
        lines.append("  • Test structural properties (type, length, non-empty) as a fallback when exact match is brittle")
    if sql:
        lines.append("  • Assert on COUNT(*) and column structure, not on specific generated values")
        lines.append("  • Use fakeit (DuckDB community extension) for realistic test data: INSTALL fakeit FROM community;")

    return "\n".join(lines)
