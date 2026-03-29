import pytest
from pathlib import Path
from blog_validate.extractor import PostBlocks
from blog_validate.languages.base import AnnotationType, CodeBlock
from blog_validate.runner import run_post, resolve_changed_posts


def block(language, code, annotation=AnnotationType.DEFAULT, fixture_name=None, index=0):
    return CodeBlock(
        language=language, code=code, annotation=annotation,
        fixture_name=fixture_name, post_slug="test-post", block_index=index,
    )


class TestRunPost:
    def test_default_sql_block_passes(self):
        post = PostBlocks(slug="test", blocks=[block("sql", "SELECT 1")])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "passed"

    def test_skip_block_is_skipped(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "import missing_module", AnnotationType.SKIP)
        ])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "skipped"

    def test_expected_failure_that_errors_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("sql", "SELECT * FROM nonexistent", AnnotationType.EXPECTED_FAILURE)
        ])
        result = run_post(post, {})
        assert result.passed
        assert result.results[0].status == "passed"

    def test_expected_failure_that_succeeds_fails_test(self):
        post = PostBlocks(slug="test", blocks=[
            block("sql", "SELECT 1", AnnotationType.EXPECTED_FAILURE)
        ])
        result = run_post(post, {})
        assert not result.passed
        assert result.results[0].status == "failed"

    def test_syntax_only_valid_python_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "x = undefined_var", AnnotationType.SYNTAX_ONLY)
        ])
        result = run_post(post, {})
        assert result.passed

    def test_assert_sql_truthy_passes(self):
        setup_block = block("sql", "CREATE TABLE t (id INT); INSERT INTO t VALUES (1),(2)",
                            AnnotationType.SETUP, index=0)
        assert_block = block("sql", "SELECT COUNT(*) = 2 FROM t", AnnotationType.ASSERT, index=1)
        result = run_post(PostBlocks(slug="test", blocks=[setup_block, assert_block]), {})
        assert result.passed

    def test_assert_sql_false_fails_test(self):
        setup_block = block("sql", "CREATE TABLE t (id INT); INSERT INTO t VALUES (1)",
                            AnnotationType.SETUP, index=0)
        assert_block = block("sql", "SELECT COUNT(*) = 99 FROM t", AnnotationType.ASSERT, index=1)
        result = run_post(PostBlocks(slug="test", blocks=[setup_block, assert_block]), {})
        assert not result.passed

    def test_assert_python_passing_assert_passes(self):
        post = PostBlocks(slug="test", blocks=[
            block("python", "assert 1 == 1", AnnotationType.ASSERT)
        ])
        result = run_post(post, {})
        assert result.passed

    def test_use_injects_fixture_before_block(self):
        fixture_block = block("sql", "CREATE TABLE users (id INT); INSERT INTO users VALUES (1)",
                              AnnotationType.FIXTURE, fixture_name="users-table")
        registry = {"users-table": fixture_block}
        use_block = block("sql", "", AnnotationType.USE, fixture_name="users-table", index=0)
        query_block = block("sql", "SELECT COUNT(*) FROM users", index=1)
        result = run_post(PostBlocks(slug="test", blocks=[use_block, query_block]), registry)
        assert result.passed

    def test_unknown_fixture_fails(self):
        use_block = block("sql", "", AnnotationType.USE, fixture_name="nonexistent", index=0)
        result = run_post(PostBlocks(slug="test", blocks=[use_block]), {})
        assert not result.passed
        assert "Unknown fixture" in result.results[0].error

    def test_dry_run_skips_all_execution(self):
        post = PostBlocks(slug="test", blocks=[block("sql", "SELECT 1")])
        result = run_post(post, {}, dry_run=True)
        assert all(r.status == "skipped" for r in result.results)

    def test_unknown_language_is_skipped(self):
        post = PostBlocks(slug="test", blocks=[block("bash", "echo hello")])
        result = run_post(post, {})
        assert result.results[0].status == "skipped"

    def test_fixture_block_in_document_is_skipped(self):
        fixture = block("sql", "CREATE TABLE t (id INT);", AnnotationType.FIXTURE,
                        fixture_name="my-table")
        result = run_post(PostBlocks(slug="test", blocks=[fixture]), {})
        assert result.results[0].status == "skipped"

    def test_helpers_file_injected_into_python_context(self, tmp_path):
        helpers = tmp_path / "blog-validate-helpers.py"
        helpers.write_text("def greet(): return 'hello'")
        post = PostBlocks(slug="test", blocks=[
            block("python", "assert greet() == 'hello'", AnnotationType.ASSERT)
        ])
        result = run_post(post, {}, helpers_path=helpers)
        assert result.passed

    def test_post_result_counts(self):
        blocks = [
            block("sql", "SELECT 1", index=0),
            block("sql", "SELECT 1", AnnotationType.SKIP, index=1),
            block("sql", "SELECT * FROM nonexistent", index=2),
        ]
        result = run_post(PostBlocks(slug="test", blocks=blocks), {})
        assert result.passed_count == 1
        assert result.skipped_count == 1
        assert result.failed_count == 1
        assert not result.passed


class TestResolveChangedPosts:
    def test_includes_directly_changed_post(self, tmp_path):
        (tmp_path / "content" / "blog" / "my-post").mkdir(parents=True)
        post = PostBlocks(slug="my-post", blocks=[])
        changed = [tmp_path / "content" / "blog" / "my-post" / "index.md"]

        result = resolve_changed_posts(changed, [post], {}, tmp_path, "content/blog", "index.md")

        assert len(result) == 1
        assert result[0].slug == "my-post"

    def test_includes_posts_that_use_a_changed_fixture(self, tmp_path):
        posts_dir = tmp_path / "content" / "blog"
        (posts_dir / "fixture-post").mkdir(parents=True)
        (posts_dir / "consumer-post").mkdir(parents=True)

        fixture_block = CodeBlock(
            language="sql", code="CREATE TABLE t (id INT);",
            annotation=AnnotationType.FIXTURE, fixture_name="my-table",
            post_slug="fixture-post", block_index=0,
        )
        use_block = CodeBlock(
            language="sql", code="",
            annotation=AnnotationType.USE, fixture_name="my-table",
            post_slug="consumer-post", block_index=0,
        )
        fixture_post = PostBlocks(slug="fixture-post", blocks=[fixture_block])
        consumer_post = PostBlocks(slug="consumer-post", blocks=[use_block])

        changed = [tmp_path / "content" / "blog" / "fixture-post" / "index.md"]
        result = resolve_changed_posts(
            changed, [fixture_post, consumer_post], {"my-table": fixture_block},
            tmp_path, "content/blog", "index.md",
        )

        slugs = {p.slug for p in result}
        assert "fixture-post" in slugs
        assert "consumer-post" in slugs

    def test_ignores_files_outside_content_path(self, tmp_path):
        post = PostBlocks(slug="my-post", blocks=[])
        changed = [tmp_path / "README.md"]

        result = resolve_changed_posts(changed, [post], {}, tmp_path, "content/blog", "index.md")

        assert result == []

    def test_returns_empty_for_no_changed_files(self, tmp_path):
        post = PostBlocks(slug="my-post", blocks=[])
        result = resolve_changed_posts([], [post], {}, tmp_path, "content/blog", "index.md")
        assert result == []
