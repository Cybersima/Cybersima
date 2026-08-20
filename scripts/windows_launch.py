#!/usr/bin/env python3
"""Windows launcher that never uses python -E (that breaks 3.14 venvs).

Version 4 / 1.5 called `.venv\\Scripts\\python.exe -E`. On Python 3.14 that
sets environment=0, ignores pyvenv.cfg home, and looks for encodings in the
SecureTrade folder — which is the fatal error the customer still sees.

This script always starts as C:\\Python314\\python.exe (or py -3). It then:
1. Removes leftover pyvenv.cfg next to start.bat (makes Python treat this folder as a venv)
2. Tries a local .venv *without* -E
3. If that interpreter cannot import encodings, runs SecureTrade with the
   working system Python 3.14 instead
"""

from __future__ import annotations

import os
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


def python_starts(python: Path) -> bool:
    if not python.is_file():
        return False
    try:
        result = subprocess.run(
            [str(python), "-c", "import encodings, sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            env=_clean_env(),
        )
    except OSError:
        return False
    return result.returncode == 0


def _clean_env() -> dict[str, str]:
    env = os.environ.copy()
    env.pop("PYTHONHOME", None)
    env.pop("PYTHONPATH", None)
    return env


def clean_stray_prefix(root: Path | None = None) -> list[str]:
    """Version 4 left pyvenv.cfg / Lib next to start.bat. That makes *any* Python look here for encodings."""
    folder = root or ROOT
    removed: list[str] = []
    cfg = folder / "pyvenv.cfg"
    if cfg.is_file():
        cfg.unlink()
        removed.append(str(cfg))
    lib = folder / "Lib"
    encodings = lib / "encodings"
    if lib.is_dir() and not encodings.exists():
        shutil.rmtree(lib, ignore_errors=True)
        removed.append(str(lib))
    return removed


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
        "Close every SecureTrade window, then run FIX-VENV.bat.\n"
        f"({last_error})"
    )


def pip_install(python: str) -> None:
    print(f"Installing CyberSym SecureTrade with {python}...")
    env = _clean_env()
    subprocess.check_call([python, "-m", "pip", "install", "-U", "pip"], cwd=ROOT, env=env)
    cmd = [python, "-m", "pip", "install", "-e", str(ROOT)]
    try:
        subprocess.check_call(cmd, cwd=ROOT, env=env)
    except subprocess.CalledProcessError:
        print("Retrying package install with --user...")
        subprocess.check_call(cmd + ["--user"], cwd=ROOT, env=env)


def app_import_ok(python: str) -> bool:
    result = subprocess.run(
        [python, "-c", "import pulsearb"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=30,
        env=_clean_env(),
    )
    return result.returncode == 0


def prepare_interpreter() -> str:
    """Return a Python executable that can import encodings and pulsearb. Never uses -E."""
    if sys.version_info < (3, 11):
        raise SystemExit("Python 3.11 or newer is required. Install it from https://www.python.org/downloads/")

    cleaned = clean_stray_prefix()
    if cleaned:
        print("Removed leftover Python files from the product folder:")
        for item in cleaned:
            print(f"  {item}")

    base = sys.executable
    if not python_starts(Path(base)):
        raise SystemExit(
            "Your installed Python cannot start. Keep using the Python 3.14 that already runs v01.3.\n"
            f"Tried: {base}"
        )

    vp = venv_python()
    if vp.is_file() and not python_starts(vp):
        print("Local .venv cannot import encodings. Removing it (data\\ CSV is kept)...")
        remove_venv()

    if not vp.is_file():
        print("Creating a fresh Python environment...")
        subprocess.check_call([base, "-m", "venv", str(VENV)], cwd=ROOT, env=_clean_env())

    if python_starts(vp):
        if not app_import_ok(str(vp)):
            pip_install(str(vp))
        if python_starts(vp) and app_import_ok(str(vp)):
            print(f"Using local environment: {vp}")
            return str(vp)

    print("The local .venv still cannot start. Using your installed Python 3.14 instead.")
    print(f"Using: {base}")
    if not app_import_ok(base):
        pip_install(base)
    return base


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    install_only = "--install-only" in args
    args = [item for item in args if item != "--install-only"]
    python = prepare_interpreter()
    if install_only:
        print("Installed. Double-click start.bat to run the dashboard.")
        return 0
    print("Starting CyberSym SecureTrade...")
    return subprocess.call([python, "-m", "pulsearb", *args], cwd=ROOT, env=_clean_env())


if __name__ == "__main__":
    raise SystemExit(main())
