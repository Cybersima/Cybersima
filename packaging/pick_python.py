"""Exit 0 only for a regular CPython 3.11–3.14 (not the free-threaded t-build)."""

from __future__ import annotations

import sys
from pathlib import Path


def usable(
    version: tuple[int, int] = sys.version_info[:2],
    executable: str = sys.executable,
    banner: str = sys.version,
) -> bool:
    name = Path(executable).name.lower()
    free_threaded = (
        "free-thread" in banner.lower()
        or name.endswith("t.exe")
        or (name.startswith("python") and name.rstrip(".exe").endswith("t"))
    )
    return version >= (3, 11) and version < (3, 15) and not free_threaded


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not usable():
        return 3 if "free-thread" in sys.version.lower() or sys.executable.lower().endswith("t.exe") else 2
    if argv:
        Path(argv[0]).write_text(f"{sys.executable}\n{sys.version_info.major}.{sys.version_info.minor}\n", encoding="utf-8")
    else:
        print(sys.executable)
        print(f"{sys.version_info.major}.{sys.version_info.minor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
