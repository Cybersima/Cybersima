#!/usr/bin/env python3
"""Build a customer zip that does not require browsing the source tree."""

from __future__ import annotations

import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "dist" / "CyberSym-SecureTrade-2.zip"
PREFIX = "CyberSym-SecureTrade-2"
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
    ".env.example",
    ".gitignore",
    "src",
    "packaging",
]


def _keep(path: Path) -> bool:
    return (
        path.is_file()
        and "__pycache__" not in path.parts
        and not any(part.endswith(".egg-info") for part in path.parts)
        and path.suffix != ".pyc"
    )


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(OUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in INCLUDE:
            path = ROOT / item
            if not path.exists():
                continue
            if path.is_file():
                zf.write(path, f"{PREFIX}/{item}")
                continue
            for file in path.rglob("*"):
                if _keep(file):
                    rel = file.relative_to(ROOT).as_posix()
                    zf.write(file, f"{PREFIX}/{rel}")
    print(OUT)


if __name__ == "__main__":
    main()
