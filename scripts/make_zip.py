#!/usr/bin/env python3
"""Build a customer zip that does not require browsing the source tree."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "CyberSym-SecureTrade-2.zip"
INCLUDE = [
    "README.md",
    "START_HERE.txt",
    "VERSION_GUIDE.md",
    "pyproject.toml",
    "requirements.txt",
    "install.sh",
    "start.sh",
    "start.bat",
    "start.command",
    "Dockerfile",
    "docker-compose.yml",
    "src",
    "packaging",
]


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in INCLUDE:
            path = ROOT / item
            if path.is_file():
                zf.write(path, item)
            else:
                for file in path.rglob("*"):
                    if file.is_file() and "__pycache__" not in file.parts:
                        zf.write(file, file.relative_to(ROOT).as_posix())
    print(OUT)


if __name__ == "__main__":
    main()
