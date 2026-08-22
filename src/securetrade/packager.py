"""Build the customer download zip — unzip, double-click, trade."""

from __future__ import annotations

import hashlib
import zipfile
from pathlib import Path

from securetrade.branding import PRODUCT, PRODUCT_SHORT, VERSION

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
    ".env.example",
    "Dockerfile",
    "docker-compose.yml",
    "src",
    "packaging",
]

SKIP_PARTS = {".git", "__pycache__", ".venv", "venv", ".pytest_cache", ".mypy_cache"}
SKIP_SUFFIXES = {".pyc", ".pyo", ".zip"}


def repo_root() -> Path:
    here = Path(__file__).resolve()
    for candidate in (here.parents[2], Path.cwd()):
        if (candidate / "pyproject.toml").exists() and (candidate / "src" / "securetrade").exists():
            return candidate
    raise FileNotFoundError("SecureTrade source tree not found")


def zip_name(version: str | None = None) -> str:
    return f"CyberSym-SecureTrade-{version or VERSION}.zip"


def folder_name(version: str | None = None) -> str:
    return f"CyberSym-SecureTrade-{version or VERSION}"


def default_zip_path(root: Path | None = None, dest_dir: Path | None = None) -> Path:
    root = root or repo_root()
    dest = dest_dir or (root / "dist")
    return dest / zip_name()


def iter_package_files(root: Path) -> list[tuple[Path, str]]:
    prefix = folder_name()
    rows: list[tuple[Path, str]] = []
    for item in INCLUDE:
        path = root / item
        if not path.exists():
            continue
        if path.is_file():
            rows.append((path, f"{prefix}/{item}"))
            continue
        for file in path.rglob("*"):
            if not file.is_file():
                continue
            if any(part in SKIP_PARTS for part in file.parts):
                continue
            if file.suffix in SKIP_SUFFIXES:
                continue
            rows.append((file, f"{prefix}/{file.relative_to(root).as_posix()}"))
    how_to = root / "packaging" / "HOW_TO_INSTALL.txt"
    terms = root / "packaging" / "TERMS.txt"
    if how_to.exists():
        rows.append((how_to, f"{prefix}/HOW_TO_INSTALL.txt"))
    if terms.exists():
        rows.append((terms, f"{prefix}/TERMS.txt"))
    return rows


def build_zip(dest: Path | None = None, root: Path | None = None) -> Path:
    root = root or repo_root()
    out = dest or default_zip_path(root)
    out.parent.mkdir(parents=True, exist_ok=True)
    files = iter_package_files(root)
    if not files:
        raise RuntimeError("Nothing to package")
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for src, arc in files:
            zf.write(src, arc)
        zf.writestr(f"{folder_name()}/VERSION.txt", f"{PRODUCT}\n{VERSION}\n")
    checksum = sha256_file(out)
    sidecar = out.with_suffix(".zip.sha256")
    sidecar.write_text(f"{checksum}  {out.name}\n", encoding="utf-8")
    return out


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def package_info(path: Path | None = None) -> dict[str, str | int | bool]:
    zip_path = path or default_zip_path()
    exists = zip_path.exists()
    return {
        "product": PRODUCT,
        "product_short": PRODUCT_SHORT,
        "version": VERSION,
        "filename": zip_path.name,
        "path": str(zip_path),
        "available": exists,
        "bytes": zip_path.stat().st_size if exists else 0,
        "sha256": sha256_file(zip_path) if exists else "",
        "download_url": "/download/zip",
    }
