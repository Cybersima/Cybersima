import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ensure_venv


def test_ensure_venv_never_rewrites_pyvenv_cfg() -> None:
    source = inspect.getsource(ensure_venv)
    assert "write_pyvenv_cfg" not in source
    assert "pyvenv.cfg" not in source


def test_windows_start_rebuilds_broken_venv() -> None:
    root = Path(__file__).resolve().parents[1]
    start = (root / "start.bat").read_text(encoding="utf-8")
    helper = (root / "scripts" / "windows-venv.bat").read_text(encoding="utf-8")
    assert "CyberSym SecureTrade 1.5" in start
    assert "windows-venv.bat" in start
    assert "import encodings" in helper
    assert "broken Version 4" in helper
    assert "rmdir /s /q .venv" in helper
    assert "pyvenv.cfg" not in helper
    assert (root / "FIX-VENV.bat").is_file()
    assert (root / "VERSION.txt").read_text(encoding="utf-8").startswith("CyberSym SecureTrade 1.5")
