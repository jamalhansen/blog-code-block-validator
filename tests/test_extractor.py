import pytest
from blog_validate.extractor import parse_annotation, extract_blocks, scan_posts, build_fixture_registry, PostBlocks
from blog_validate.languages.base import AnnotationType


class TestParseAnnotation:
    def test_parses_skip(self):
        assert parse_annotation("<!-- test:skip -->") == (AnnotationType.SKIP, None)

    def test_parses_expected_failure(self):
        assert parse_annotation("<!-- test:expected-failure -->") == (AnnotationType.EXPECTED_FAILURE, None)

    def test_parses_setup(self):
        assert parse_annotation("<!-- test:setup -->") == (AnnotationType.SETUP, None)

    def test_parses_syntax_only(self):
        assert parse_annotation("<!-- test:syntax-only -->") == (AnnotationType.SYNTAX_ONLY, None)

    def test_parses_assert(self):
        assert parse_annotation("<!-- test:assert -->") == (AnnotationType.ASSERT, None)

    def test_parses_fixture_with_name(self):
        assert parse_annotation('<!-- test:fixture name="my-table" -->') == (AnnotationType.FIXTURE, "my-table")

    def test_parses_use_with_name(self):
        assert parse_annotation('<!-- test:use name="my-table" -->') == (AnnotationType.USE, "my-table")

    def test_returns_none_for_plain_text(self):
        assert parse_annotation("Some text") is None

    def test_returns_none_for_code_fence(self):
        assert parse_annotation("```python") is None

    def test_returns_none_for_empty_string(self):
        assert parse_annotation("") is None

    def test_returns_none_for_unknown_type(self):
        assert parse_annotation("<!-- test:unknown -->") is None


class TestExtractBlocks:
    def test_extracts_bare_code_block_as_default(self):
        blocks = extract_blocks("```python\nx = 1\n```", "my-post")
        assert len(blocks) == 1
        assert blocks[0].language == "python"
        assert blocks[0].code == "x = 1"
        assert blocks[0].annotation == AnnotationType.DEFAULT

    def test_extracts_annotated_block(self):
        content = "<!-- test:skip -->\n```python\nimport missing\n```"
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 1
        assert blocks[0].annotation == AnnotationType.SKIP

    def test_extracts_fixture_block_with_name(self):
        content = '<!-- test:fixture name="users-table" -->\n```sql\nCREATE TABLE users (id INT);\n```'
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].annotation == AnnotationType.FIXTURE
        assert blocks[0].fixture_name == "users-table"

    def test_multiple_blocks_in_document_order(self):
        content = (
            "```python\nx = 1\n```\n\n"
            "<!-- test:skip -->\n```sql\nSELECT 1\n```\n\n"
            "```python\ny = 2\n```"
        )
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 3
        assert blocks[0].annotation == AnnotationType.DEFAULT
        assert blocks[1].annotation == AnnotationType.SKIP
        assert blocks[2].annotation == AnnotationType.DEFAULT

    def test_block_indices_increment(self):
        content = "```python\nx = 1\n```\n```python\ny = 2\n```"
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].block_index == 0
        assert blocks[1].block_index == 1

    def test_post_slug_set_on_blocks(self):
        blocks = extract_blocks("```python\nx = 1\n```", "my-slug")
        assert blocks[0].post_slug == "my-slug"

    def test_orphaned_annotation_not_applied(self):
        content = "<!-- test:skip -->\nSome text here\n```python\nx = 1\n```"
        blocks = extract_blocks(content, "my-post")
        assert len(blocks) == 1
        assert blocks[0].annotation == AnnotationType.DEFAULT

    def test_blank_lines_between_annotation_and_fence_ok(self):
        content = "<!-- test:skip -->\n\n```python\nx = 1\n```"
        blocks = extract_blocks(content, "my-post")
        assert blocks[0].annotation == AnnotationType.SKIP

    def test_returns_empty_for_no_code_blocks(self):
        blocks = extract_blocks("Just some text\nNo code here", "my-post")
        assert blocks == []


class TestScanPosts:
    def test_scans_posts_from_content_dir(self, tmp_path):
        post_dir = tmp_path / "content" / "blog" / "my-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("```python\nx = 1\n```")

        posts = scan_posts(tmp_path, "content/blog", "index.md")

        assert len(posts) == 1
        assert posts[0].slug == "my-post"
        assert len(posts[0].blocks) == 1

    def test_ignores_files_not_directories(self, tmp_path):
        posts_dir = tmp_path / "content" / "blog"
        posts_dir.mkdir(parents=True)
        (posts_dir / "_index.md").write_text("---\n---\n")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert posts == []

    def test_returns_empty_for_missing_content_path(self, tmp_path):
        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert posts == []

    def test_posts_sorted_by_slug(self, tmp_path):
        for slug in ["zzz-post", "aaa-post", "mmm-post"]:
            d = tmp_path / "content" / "blog" / slug
            d.mkdir(parents=True)
            (d / "index.md").write_text("```python\nx = 1\n```")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        slugs = [p.slug for p in posts]
        assert slugs == sorted(slugs)

    def test_post_with_no_code_blocks_still_included(self, tmp_path):
        post_dir = tmp_path / "content" / "blog" / "prose-post"
        post_dir.mkdir(parents=True)
        (post_dir / "index.md").write_text("Just text, no code.")

        posts = scan_posts(tmp_path, "content/blog", "index.md")
        assert len(posts) == 1
        assert posts[0].blocks == []


class TestBuildFixtureRegistry:
    def test_registers_fixture_blocks(self):
        from blog_validate.languages.base import CodeBlock
        block = CodeBlock(
            language="sql", code="CREATE TABLE t (id INT);",
            annotation=AnnotationType.FIXTURE, fixture_name="my-table",
            post_slug="post-1", block_index=0,
        )
        registry = build_fixture_registry([PostBlocks(slug="post-1", blocks=[block])])
        assert "my-table" in registry
        assert registry["my-table"].code == "CREATE TABLE t (id INT);"

    def test_ignores_non_fixture_blocks(self):
        from blog_validate.languages.base import CodeBlock
        block = CodeBlock(
            language="sql", code="SELECT 1",
            annotation=AnnotationType.DEFAULT,
            post_slug="post-1", block_index=0,
        )
        registry = build_fixture_registry([PostBlocks(slug="post-1", blocks=[block])])
        assert len(registry) == 0

    def test_collects_fixtures_across_multiple_posts(self):
        from blog_validate.languages.base import CodeBlock
        posts = [
            PostBlocks(slug="post-1", blocks=[
                CodeBlock(language="sql", code="CREATE TABLE a (id INT);",
                         annotation=AnnotationType.FIXTURE, fixture_name="table-a",
                         post_slug="post-1", block_index=0)
            ]),
            PostBlocks(slug="post-2", blocks=[
                CodeBlock(language="sql", code="CREATE TABLE b (id INT);",
                         annotation=AnnotationType.FIXTURE, fixture_name="table-b",
                         post_slug="post-2", block_index=0)
            ]),
        ]
        registry = build_fixture_registry(posts)
        assert "table-a" in registry
        assert "table-b" in registry
