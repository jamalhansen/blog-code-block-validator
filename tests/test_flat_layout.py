from blog_validate.extractor import scan_posts
from blog_validate.runner import resolve_changed_posts

def test_scan_posts_flat(tmp_path):
    # Setup flat layout
    content_dir = tmp_path / "obsidian"
    content_dir.mkdir()
    (content_dir / "pattern-01.md").write_text("```python\nprint('hello')\n```")
    (content_dir / "pattern-02.md").write_text("```python\nprint('world')\n```")
    (content_dir / "other.txt").write_text("not a markdown file")

    results = scan_posts(tmp_path, "obsidian", "unused.md", layout="flat")
    
    assert len(results) == 2
    slugs = {r.slug for r in results}
    assert slugs == {"pattern-01", "pattern-02"}
    assert results[0].blocks[0].code == "print('hello')" or results[1].blocks[0].code == "print('hello')"

def test_resolve_changed_posts_flat(tmp_path):
    content_dir = tmp_path / "obsidian"
    content_dir.mkdir()
    p1 = content_dir / "p1.md"
    p1.write_text("```python\n1\n```")
    
    all_posts = scan_posts(tmp_path, "obsidian", "unused.md", layout="flat")
    
    # Simulate change to p1.md
    changed_files = [p1]
    affected = resolve_changed_posts(
        changed_files,
        all_posts,
        fixture_registry={},
        repo_root=tmp_path,
        content_path="obsidian",
        post_file="unused.md",
        layout="flat"
    )
    
    assert len(affected) == 1
    assert affected[0].slug == "p1"
