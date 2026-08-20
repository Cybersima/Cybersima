#!/usr/bin/env python3
"""Create or rebuild the local environment. Delegates to windows_launch (no -E, no pyvenv.cfg rewrite)."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from windows_launch import prepare_interpreter


def main() -> None:
    prepare_interpreter()


if __name__ == "__main__":
    main()
