from dataclasses import dataclass, field
from pathlib import Path
import tomllib


@dataclass
class BlogConfig:
    content_path: str = "content/blog"
    post_file: str = "index.md"
    layout: str = "bundle"  # "bundle", "flat", or "vault"
    exclude_patterns: list[str] = field(default_factory=list)
    helpers_path: str = "blog-validate-helpers"
    # Posts whose frontmatter `status` is in this list are not executed, e.g.
    # ["dropped", "outline"] for vault drafts: an outline's code is a sketch
    # and a dropped post's code is never going to be fixed.
    skip_statuses: list[str] = field(default_factory=list)


@dataclass
class SqlConfig:
    backend: str = "duckdb"


@dataclass
class BashConfig:
    # false = syntax-check bash blocks only. Unreviewed drafts contain
    # commands like `brew install`, `mkdir ~/bin` and git history rewrites
    # that must never run unattended on the author's machine.
    execute: bool = True


@dataclass
class PythonConfig:
    dependencies: list[str] = field(default_factory=list)
    # Virtualenv whose site-packages the executed blocks may import from.
    # Defaults to <config root>/.venv; set it when the config lives somewhere
    # other than the project that owns the dependencies (e.g. configs/vault.toml
    # validating vault drafts against the blog repo's .venv).
    venv: str | None = None


@dataclass
class Config:
    blog: BlogConfig
    sql: SqlConfig
    python: PythonConfig
    root: Path
    bash: BashConfig = field(default_factory=BashConfig)


def resolve_content_root(blog_root: Path, content_path: str) -> Path:
    """Join content_path onto blog_root, honoring absolute paths and `~`."""
    p = Path(content_path).expanduser()
    return p if p.is_absolute() else blog_root / p


def _build_config(toml_path: Path, root: Path) -> Config:
    with open(toml_path, "rb") as f:
        data = tomllib.load(f)
    config = Config(
        blog=BlogConfig(**data.get("blog", {})),
        sql=SqlConfig(**data.get("sql", {})),
        python=PythonConfig(**data.get("python", {})),
        root=root,
        bash=BashConfig(**data.get("bash", {})),
    )
    valid_layouts = {"bundle", "flat", "vault"}
    if config.blog.layout not in valid_layouts:
        raise ValueError(
            f"Invalid layout {config.blog.layout!r} in {toml_path}. "
            f"Valid options: {', '.join(sorted(valid_layouts))}"
        )
    return config


def load_config(start_dir: Path, config_path: Path | None = None) -> Config:
    """Load blog-validate.toml, either from an explicit path or by walking up from start_dir."""
    if config_path is not None:
        toml_path = config_path.expanduser().resolve()
        if not toml_path.exists():
            raise FileNotFoundError(f"Config file not found: {toml_path}")
        return _build_config(toml_path, toml_path.parent)

    current = start_dir.resolve()
    while True:
        toml_path = current / "blog-validate.toml"
        if toml_path.exists():
            return _build_config(toml_path, current)
        parent = current.parent
        if parent == current:
            raise FileNotFoundError(
                "blog-validate.toml not found in any parent directory"
            )
        current = parent
