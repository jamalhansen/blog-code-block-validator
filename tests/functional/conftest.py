import pytest
import textwrap


@pytest.fixture
def hugo_blog_factory(tmp_path):
    def _create(config_overrides=None):
        blog_root = tmp_path / "hugo_blog"
        blog_root.mkdir()
        content_dir = blog_root / "content" / "blog"
        content_dir.mkdir(parents=True)

        # Config
        config = textwrap.dedent("""
            [blog]
            content_path = "content/blog"
            post_file = "index.md"
            layout = "bundle"
        """)
        (blog_root / "blog-validate.toml").write_text(config)

        # Flat post
        flat_post = content_dir / "flat-post"
        flat_post.mkdir()
        (flat_post / "index.md").write_text(textwrap.dedent("""
            # Flat Post
            ```python
            print("hello")
            ```
            ```sql
            SELECT 1;
            ```
        """))

        # Annotated flat post
        annotated_post = content_dir / "annotated-flat-post"
        annotated_post.mkdir()
        (annotated_post / "index.md").write_text(textwrap.dedent("""
            # Annotated Post
            <!-- test:skip -->
            ```python
            exit(1)
            ```
            <!-- test:expected-failure -->
            ```python
            1/0
            ```
            <!-- test:setup name="myfixture" -->
            ```python
            x = 42
            ```
            <!-- test:fixture name="myfixture" -->
            ```python
            y = x + 1
            ```
        """))

        # SQL series
        sql_series = content_dir / "sql-series"
        sql_series.mkdir()
        
        intro = sql_series / "01-intro"
        intro.mkdir()
        (intro / "index.md").write_text("```sql\nSELECT 1;\n```")
        
        joins = sql_series / "02-joins"
        joins.mkdir()
        (joins / "index.md").write_text("```sql\nSELECT 1 as id;\n```\n```python\nprint('joins')\n```")

        # Mixed series
        mixed_series = content_dir / "mixed-series"
        mixed_series.mkdir()
        post1 = mixed_series / "01-post"
        post1.mkdir()
        (post1 / "index.md").write_text("<!-- test:expected-failure -->\n```python\nraise ValueError()\n```")

        return blog_root
    return _create


@pytest.fixture
def obsidian_vault_factory(tmp_path):
    def _create():
        vault_root = tmp_path / "obsidian_vault"
        vault_root.mkdir()
        blog_dir = vault_root / "blog"
        blog_dir.mkdir()

        # Config
        config = textwrap.dedent("""
            [blog]
            content_path = "blog"
            layout = "vault"
            exclude_patterns = ["promo.md"]
        """)
        (vault_root / "blog-validate.toml").write_text(config)

        # SQL Series in vault
        series_dir = blog_dir / "series" / "sql-series" / "posts"
        series_dir.mkdir(parents=True)
        
        intro_dir = series_dir / "01-intro"
        intro_dir.mkdir()
        (intro_dir / "intro-post.md").write_text("```sql\nSELECT 1;\n```")
        (intro_dir / "promo.md").write_text("Buy my course!")
        
        joins_dir = series_dir / "02-joins"
        joins_dir.mkdir()
        (joins_dir / "joins-post.md").write_text("```sql\nSELECT 1;\n```\n```python\nprint('joins')\n```")

        # Another series
        another_dir = blog_dir / "series" / "another-series" / "posts" / "01-first"
        another_dir.mkdir(parents=True)
        (another_dir / "first-post.md").write_text("```python\nprint('first')\n```")

        return vault_root
    return _create
