"""Return 0 if .venv was created by this Python, 1 if it belongs to another install."""

from __future__ import annotations

import sys
from pathlib import Path


def venv_home(cfg: Path) -> Path | None:
    if not cfg.is_file():
        return None
    text = cfg.read_text(encoding="utf-8", errors="ignore")
    for line in text.splitlines():
        key, _, value = line.partition("=")
        if key.strip().lower() == "home" and value.strip():
            return Path(value.strip().strip('"')).expanduser()
    return None


def matches(cfg: Path, base_prefix: Path) -> bool:
    home = venv_home(cfg)
    if home is None:
        return False
    try:
        return home.resolve() == base_prefix.resolve()
    except OSError:
        return False


def main() -> int:
    cfg = Path(".venv") / "pyvenv.cfg"
    if not Path(".venv").exists():
        return 0
    if matches(cfg, Path(sys.base_prefix)):
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
