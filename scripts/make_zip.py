#!/usr/bin/env python3
"""Build a branded zip you can copy to another computer."""

from __future__ import annotations

import stat
import sys
import zipfile
from pathlib import Path

SKIP_DIRS = {".git", ".venv", ".pytest_cache", "__pycache__", "dist", ".mypy_cache", "releases", "data"}
SKIP_NAMES = {"PulseArb.zip", "CyberSym-SecureTrade.zip"}
EXECUTABLE = {"start.sh", "start.command", "install.sh", "make-zip.sh", "Install.command", "Open-Report.sh", "go-live.sh", "Go-Live.command"}
FOLDER = "CyberSym-SecureTrade"


def should_skip(rel: Path) -> bool:
    if any(part in SKIP_DIRS for part in rel.parts):
        return True
    if any(part.endswith(".egg-info") for part in rel.parts):
        return True
    if rel.name in SKIP_NAMES or rel.name.endswith(".egg-info"):
        return True
    if rel.suffix == ".pyc":
        return True
    if rel.parts and rel.parts[0] == "keys" and rel.suffix.lower() in {".json", ".pem", ".key"}:
        return True
    if rel.parts and rel.parts[0] == "branding" and rel.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg"}:
        return True
    return False


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "releases" / "CyberSym-SecureTrade.zip"
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()

    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(root.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(root)
            if should_skip(rel):
                continue
            arcname = f"{FOLDER}/{rel.as_posix()}"
            info = zipfile.ZipInfo.from_file(path, arcname)
            if path.name in EXECUTABLE or path.suffix in {".sh", ".command"}:
                info.external_attr = (stat.S_IFREG | 0o755) << 16
            with path.open("rb") as handle:
                zf.writestr(info, handle.read())

    print(f"Wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
