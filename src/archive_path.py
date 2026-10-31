"""Single place that builds the path of the digitized CIRED archive.

Host convention: `$DATASETS_DIR/ours/Archives CIRED numerisées`. When the session
did not load the variable (plain ssh), fall back to the host declaration file.
"""
import os
from pathlib import Path

VAR = "DATASETS_DIR"
CONF_PATH = Path.home() / ".config" / "environment.d" / "50-datasets.conf"
SUBPATH = Path("ours") / "Archives CIRED numerisées"


def _from_conf(conf_path: Path) -> str | None:
    try:
        lines = conf_path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return None
    for line in lines:
        line = line.strip()
        if line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        if key.strip() == VAR and value.strip():
            return value.strip().strip("\"'")
    return None


def archive_dir(conf_path: Path | None = None) -> Path:
    """Return the archive root; exit with a clear message if undeclared."""
    conf_path = CONF_PATH if conf_path is None else conf_path
    base = os.environ.get(VAR) or _from_conf(conf_path)
    if not base:
        raise SystemExit(
            f"{VAR} is not set and not declared in {conf_path}; "
            f"set it or pass --archive-dir explicitly."
        )
    return Path(base) / SUBPATH
