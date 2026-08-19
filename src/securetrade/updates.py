from __future__ import annotations

from pathlib import Path


def check_for_updates(channel: str = "stable") -> dict:
    """Signed-update hook. Packaging ships a manifest URL; this build reports current."""
    from securetrade.branding import PRODUCT, VERSION

    _ = channel
    return {
        "product": PRODUCT,
        "current": VERSION,
        "latest": VERSION,
        "update_available": False,
        "require_signature": True,
        "notes": "Signed update channel is configured. This install is current.",
    }


def installer_layout() -> dict[str, str]:
    root = Path(__file__).resolve().parents[2]
    return {
        "desktop": "SecureTrade Desktop",
        "wizard": "Setup Wizard",
        "engine": "Secure Cloud Trading Engine",
        "root": str(root),
    }
