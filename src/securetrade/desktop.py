from __future__ import annotations

"""Thin desktop launcher. The engine keeps running independently (Docker/VPS)."""

from securetrade.cli import main


def launch() -> None:
    main(["desktop"])
