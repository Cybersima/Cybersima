"""CyberSym product identity — user-facing name and signature."""

from pathlib import Path

COMPANY = "CyberSym"
PRODUCT = "CyberSym SecureTrade"
PRODUCT_SHORT = "SecureTrade"
VERSION = "1.5"
SIGNATURE = "A CyberSym product"
COPYRIGHT = "© CyberSym. All rights reserved."
USER_AGENT = "CyberSym-SecureTrade/1.5"

# Drop the official crest in branding/ next to start.bat.
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


def resolve_logo_path(web_dir: Path, cwd: Path | None = None) -> Path:
    folder = (cwd or Path.cwd()) / "branding"
    for name in CUSTOM_LOGO_NAMES:
        path = folder / name
        if path.is_file():
            return path
    return web_dir / "static" / "logo.png"
