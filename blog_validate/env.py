import sys
import glob
from pathlib import Path
import importlib.util


def setup_environment(
    root: Path, dependencies: list[str] | None = None, venv: str | None = None
) -> None:
    """Set up the Python environment for validation."""
    # 1. Add the venv's site-packages to sys.path
    venv_path = Path(venv).expanduser() if venv else root / ".venv"
    if not venv_path.is_absolute():
        venv_path = root / venv_path
    if venv_path.exists():
        # Handle different platforms (lib/pythonX.Y/site-packages on Unix, Lib/site-packages on Windows)
        site_packages = glob.glob(str(venv_path / "lib" / "python*" / "site-packages"))
        if not site_packages:
            site_packages = glob.glob(str(venv_path / "Lib" / "site-packages"))

        for sp in site_packages:
            if sp not in sys.path:
                sys.path.insert(0, sp)

    # 2. Check for missing dependencies. Warnings go to stderr so that
    # `check --json` still emits clean JSON on stdout.
    if dependencies:
        missing = []
        _pkg_to_mod = {"pyyaml": "yaml"}
        for dep in dependencies:
            mod_name = _pkg_to_mod.get(dep.lower(), dep.replace("-", "_"))
            if importlib.util.find_spec(mod_name) is None:
                missing.append(dep)

        if missing:
            print(
                f"Warning: Missing dependencies declared in blog-validate.toml: {', '.join(missing)}",
                file=sys.stderr,
            )
            print(f"Try running: uv pip install {' '.join(missing)}", file=sys.stderr)
