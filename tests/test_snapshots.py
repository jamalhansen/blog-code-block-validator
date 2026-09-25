from blog_validate import snapshots
from blog_validate.extractor import PostBlocks
from blog_validate.languages import make_context
from blog_validate.languages.base import AnnotationType, CodeBlock
from blog_validate.languages.python import PythonValidator
from blog_validate.languages.sql import SQLValidator
from blog_validate.runner import run_post


def _post(*codes: tuple[str, str], slug: str = "p") -> PostBlocks:
    blocks = [CodeBlock(language=lang, code=code, annotation=AnnotationType.DEFAULT, post_slug=slug, block_index=i)
              for i, (lang, code) in enumerate(codes)]
    return PostBlocks(slug=slug, blocks=blocks)


def _run(post: PostBlocks):
    return run_post(post, {}, print_fn=lambda s: None)


SETUP = ("sql", "CREATE TABLE t AS SELECT * FROM (VALUES (1, 'a'), (2, 'b')) v(id, name)")
QUERY = ("sql", "SELECT id, name FROM t")


class TestFingerprints:
    def test_sql_query_fingerprint_ignores_row_order(self):
        ctx = make_context()
        SQLValidator().execute(SETUP[1], ctx)
        assert ctx.last_result["columns"] == ["Count"]  # DuckDB reports rows written; a data change shows here too
        SQLValidator().execute("SELECT id, name FROM t ORDER BY id", ctx)
        asc = ctx.last_result
        SQLValidator().execute("SELECT id, name FROM t ORDER BY id DESC", ctx)
        assert asc == ctx.last_result
        assert asc["columns"] == ["id", "name"] and asc["rows"] == 2

    def test_explain_is_never_fingerprinted(self):
        ctx = make_context()
        SQLValidator().execute(SETUP[1], ctx)
        SQLValidator().execute("-- plan\nEXPLAIN ANALYZE SELECT * FROM t", ctx)
        assert ctx.last_result is None

    def test_python_stdout_fingerprint(self):
        ctx = make_context()
        PythonValidator().execute("print('hello')", ctx)
        assert ctx.last_result["stdout"] == "hello\n"


class TestRecordAndApply:
    def test_block_keys_are_code_hash_plus_occurrence(self):
        keys = snapshots.block_keys(["a", "b", "a"])
        assert keys[0] != keys[1] and keys[0].split("#")[0] == keys[2].split("#")[0]
        assert keys[0].endswith("#1") and keys[2].endswith("#2")

    def test_unchanged_output_passes_and_changed_output_fails(self):
        post = _post(SETUP, QUERY)
        recorded = snapshots.record(_run(post), _run(post), _run(post))
        assert len(recorded) == 2 and not any(v.get("unstable") for v in recorded.values())

        ok = _run(post)
        assert snapshots.apply(ok, recorded) == 2 and ok.passed

        changed = _run(_post(("sql", "CREATE TABLE t AS SELECT * FROM (VALUES (1, 'a')) v(id, name)"), QUERY))
        snapshots.apply(changed, recorded)
        assert not changed.passed
        assert "row count changed: 2 -> 1" in changed.results[1].error
        assert "snapshot --post p" in changed.results[1].hint

    def test_editing_a_block_retires_its_snapshot(self):
        recorded = snapshots.record(_run(_post(SETUP, QUERY)), _run(_post(SETUP, QUERY)))
        edited = _run(_post(SETUP, ("sql", "SELECT name FROM t")))
        assert snapshots.apply(edited, recorded) == 1 and edited.passed  # only the unchanged setup

    def test_output_that_varies_between_runs_is_unstable(self):
        post = _post(("python", "import uuid; print(uuid.uuid4())"))
        recorded = snapshots.record(_run(post), _run(post))
        assert list(recorded.values()) == [{"unstable": True}]
        assert snapshots.apply(_run(post), recorded) == 0

    def test_save_and_load_round_trip(self, tmp_path):
        path = tmp_path / "blog-validate.snapshots.json"
        snapshots.save(path, {"b": {"k#1": {"rows": 1}}, "a": {}})
        assert snapshots.load(path) == {"b": {"k#1": {"rows": 1}}}
        assert snapshots.load(tmp_path / "missing.json") == {}
