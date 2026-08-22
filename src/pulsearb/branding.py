"""CyberSym product identity — user-facing name and signature."""

from __future__ import annotations

from pathlib import Path

COMPANY = "CyberSym"
PRODUCT = "CyberSym SecureTrade"
PRODUCT_SHORT = "SecureTrade"
SIGNATURE = "A CyberSym product"
COPYRIGHT = "© CyberSym. All rights reserved."
USER_AGENT = "CyberSym-SecureTrade/0.1"

# Drop the official crest in branding/ next to start.bat.
LOGO_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
CUSTOM_LOGO_NAMES = (
    "cybersym-logo.png",
    "cybersym-logo.jpg",
    "cybersym-logo.jpeg",
    "cybersym-logo.webp",
    "logo.png",
    "logo.jpg",
    "logo.jpeg",
    "logo.webp",
)


def _is_logo_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() in LOGO_SUFFIXES


def branding_folders(web_dir: Path, cwd: Path | None = None) -> list[Path]:
    folders: list[Path] = []
    seen: set[Path] = set()

    def add(path: Path) -> None:
        try:
            key = path.resolve()
        except OSError:
            key = path
        if key in seen:
            return
        seen.add(key)
        folders.append(path)

    add((cwd or Path.cwd()) / "branding")
    try:
        resolved = web_dir.resolve()
        pkg = resolved.parent
        src = pkg.parent
        if resolved.name == "web" and pkg.name == "pulsearb" and src.name == "src":
            add(src.parent / "branding")
    except OSError:
        pass
    return folders


def resolve_logo_path(web_dir: Path, cwd: Path | None = None) -> Path:
    folders = branding_folders(web_dir, cwd)
    for folder in folders:
        for name in CUSTOM_LOGO_NAMES:
            path = folder / name
            if path.is_file():
                return path
    extras: list[Path] = []
    for folder in folders:
        if not folder.is_dir():
            continue
        extras.extend(path for path in folder.iterdir() if _is_logo_file(path))
    if extras:
        return max(extras, key=lambda path: path.stat().st_mtime)
    root = cwd or Path.cwd()
    for name in ("cybersym-logo.png", "cybersym-logo.jpg", "logo.png"):
        path = root / name
        if path.is_file():
            return path
    return web_dir / "static" / "logo.png"


def logo_version(path: Path) -> str:
    try:
        return str(int(path.stat().st_mtime))
    except OSError:
        return "0"


def install_logo(source: Path, *, cwd: Path | None = None) -> Path:
    """Copy an image into branding/cybersym-logo.* so the dashboard can find it."""
    src = Path(source).expanduser()
    if not src.is_file():
        raise FileNotFoundError(f"That image is missing: {src}")
    ext = src.suffix.lower()
    if ext not in LOGO_SUFFIXES:
        raise ValueError("Use a PNG, JPG, or WebP image.")
    dest_dir = (cwd or Path.cwd()) / "branding"
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"cybersym-logo{ext}"
    payload = src.read_bytes()
    for name in CUSTOM_LOGO_NAMES:
        old = dest_dir / name
        if old.exists() and old.resolve() != dest.resolve() and old.resolve() != src.resolve():
            old.unlink()
    dest.write_bytes(payload)
    return dest
