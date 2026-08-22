#!/usr/bin/env python3
"""Build a customer zip that does not require browsing the source tree."""

from __future__ import annotations

from securetrade.packager import build_zip, package_info


def main() -> None:
    path = build_zip()
    info = package_info(path)
    print(path)
    print("sha256", info["sha256"])
    print("bytes", info["bytes"])


if __name__ == "__main__":
    main()
