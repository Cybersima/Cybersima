#!/usr/bin/env python3
"""Create or repair the local .venv so Windows launchers can import encodings."""

from __future__ import annotations

import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENV = ROOT / ".venv"


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def venv_ok(python: Path) -> bool:
    if not python.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python), "-c", "import encodings, sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except OSError:
        return False
    return result.returncode == 0


def write_pyvenv_cfg(venv_dir: Path, home: str, executable: str, version: str) -> None:
    (venv_dir / "pyvenv.cfg").write_text(
        (
            f"home = {home}\n"
            f"include-system-site-packages = false\n"
            f"version = {version}\n"
            f"executable = {executable}\n"
            f"command = {executable} -m venv {venv_dir}\n"
        ),
        encoding="utf-8",
    )


def remove_venv() -> None:
    if not VENV.exists():
        return
    last_error: OSError | None = None
    for _ in range(5):
        try:
            shutil.rmtree(VENV)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.6)
    raise SystemExit(
        "Could not remove the broken .venv folder.\n"
        "Close every SecureTrade window, then run REPAIR.bat.\n"
        f"({last_error})"
    )


def create_venv() -> None:
    print("Creating a fresh Python environment...")
    subprocess.check_call([sys.executable, "-m", "venv", str(VENV), "--clear"], cwd=ROOT)


def install_app(python: Path) -> None:
    print("Installing CyberSym SecureTrade into .venv...")
    subprocess.check_call([str(python), "-m", "pip", "install", "-U", "pip"], cwd=ROOT)
    subprocess.check_call([str(python), "-m", "pip", "install", "-e", "."], cwd=ROOT)


def main() -> None:
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required. Install it from https://www.python.org/downloads/")
    python = venv_python()
    if venv_ok(python):
        probe = subprocess.run(
            [str(python), "-c", "import pulsearb"],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )
        if probe.returncode == 0:
            return
        print("Python is OK, but SecureTrade needs to be installed into .venv...")
        install_app(python)
        return
    print("The local Python environment is broken or missing. Repairing...")
    remove_venv()
    create_venv()
    python = venv_python()
    if not venv_ok(python):
        raise SystemExit(
            "Python still cannot start after rebuilding .venv.\n"
            "Use the same Python 3.14 (or 3.11+) that already runs v01.3,\n"
            "close other SecureTrade windows, then run REPAIR.bat again."
        )
    install_app(python)


if __name__ == "__main__":
    main()
