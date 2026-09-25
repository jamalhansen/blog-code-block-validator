"""Snapshot testing: a block must keep producing what it produced when recorded.

Most blocks only prove "it runs". A snapshot records what each block returned -- a
query's columns, row count and a digest of the rows; a Python block's stdout -- in a
JSON file next to the config (never in the post), and `check` fails a block whose
output changes. Blocks are keyed by a hash of their code plus its occurrence in the
post, so editing a block retires its snapshot instead of failing it. Recording runs
each post three times; a block whose output differs between runs (random data,
timestamps) is stored as unstable and never compared. Row order is ignored.
"""
import hashlib
import json
from pathlib import Path

from blog_validate.runner import PostResult

VERSION = 1


def block_keys(codes: list[str]) -> list[str]:
    seen: dict[str, int] = {}
    keys = []
    for code in codes:
        h = hashlib.sha256(code.encode()).hexdigest()[:12]
        seen[h] = seen.get(h, 0) + 1
        keys.append(f"{h}#{seen[h]}")
    return keys


def load(path: Path) -> dict[str, dict[str, dict]]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8")).get("posts", {})


def save(path: Path, posts: dict[str, dict[str, dict]]) -> None:
    ordered = {slug: dict(sorted(v.items())) for slug, v in sorted(posts.items()) if v}
    path.write_text(json.dumps({"version": VERSION, "posts": ordered}, indent=2) + "\n", encoding="utf-8")


def _entries(result: PostResult) -> dict[str, dict]:
    keys = block_keys([r.block.code for r in result.results])
    return {k: r.fingerprint for k, r in zip(keys, result.results) if r.status == "passed" and r.fingerprint}


RUNS = 3


def record(*runs: PostResult) -> dict[str, dict]:
    """Stable fingerprints across runs of one post; any that differ become {"unstable": true}."""
    first, *rest = [_entries(r) for r in runs]
    return {k: (v if all(o.get(k) == v for o in rest) else {"unstable": True}) for k, v in first.items()}


def describe_change(old: dict, new: dict | None) -> str:
    if new is None:
        return "no longer produces output"
    if "columns" in old:
        if old.get("columns") != new.get("columns"):
            return f"columns changed: {old['columns']} -> {new.get('columns')}"
        if old.get("rows") != new.get("rows"):
            return f"row count changed: {old['rows']} -> {new.get('rows')}"
        return "rows changed (same columns and count)"
    return f"output changed: {old.get('stdout', '')[:60]!r} -> {(new.get('stdout') or '')[:60]!r}"


def apply(result: PostResult, recorded: dict[str, dict]) -> int:
    """Fail passed blocks whose output no longer matches their snapshot. Returns how many were compared."""
    keys = block_keys([r.block.code for r in result.results])
    compared = 0
    for key, r in zip(keys, result.results):
        old = recorded.get(key)
        if r.status != "passed" or not old or old.get("unstable"):
            continue
        compared += 1
        if r.fingerprint != old:
            r.status = "failed"
            r.error = f"Output changed since snapshot: {describe_change(old, r.fingerprint)}"
            r.hint = f"If the change is intended, re-record: blog-validate snapshot --post {result.slug}"
    return compared
