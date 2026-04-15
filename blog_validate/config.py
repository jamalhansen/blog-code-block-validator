from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class BlogConfig:
    content_path: str = "content/blog"
    post_file: str = "index.md"
    layout: str = "bundle"  # "bundle", "flat", or "vault"
    exclude_patterns: list[str] = field(default_factory=list)


@dataclass
class SqlConfig:
    backend: str = "duckdb"


@dataclass
class Config:
    blog: BlogConfig
    sql: SqlConfig
    root: Path


def load_config(start_dir: Path) -> Config:
    """Walk up from start_dir to find blog-validate.toml."""
    current = start_dir.resolve()
    while True:
        toml_path = current / "blog-validate.toml"
        if toml_path.exists():
            with open(toml_path, "rb") as f:
                data = tomllib.load(f)
            return Config(
                blog=BlogConfig(**data.get("blog", {})),
                sql=SqlConfig(**data.get("sql", {})),
                root=current,
            )
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "blog-validate.toml not found in any parent directory"
            )
        current = parent
