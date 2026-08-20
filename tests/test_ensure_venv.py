import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import ensure_venv
import windows_launch


def test_ensure_venv_never_rewrites_pyvenv_cfg() -> None:
    source = inspect.getsource(ensure_venv)
    assert "write_pyvenv_cfg" not in source
    launch = inspect.getsource(windows_launch)
    assert "write_pyvenv_cfg" not in launch
    assert '"-E"' not in launch
    assert "'-E'" not in launch


def test_windows_start_uses_system_python_without_isolated_mode() -> None:
    root = Path(__file__).resolve().parents[1]
    start = (root / "start.bat").read_text(encoding="utf-8")
    assert "CyberSym SecureTrade 1.6" in start
    assert "windows_launch.py" in start
    assert " -E " not in start
    assert "-E -m pulsearb" not in start
    assert (root / "FIX-VENV.bat").is_file()
    assert (root / "VERSION.txt").read_text(encoding="utf-8").startswith("CyberSym SecureTrade 1.6")


def test_clean_stray_prefix_removes_root_pyvenv_cfg(tmp_path: Path) -> None:
    (tmp_path / "pyvenv.cfg").write_text("home = C:\\Broken\n", encoding="utf-8")
    fake_lib = tmp_path / "Lib"
    fake_lib.mkdir()
    (fake_lib / "not-stdlib.txt").write_text("x", encoding="utf-8")
    removed = windows_launch.clean_stray_prefix(tmp_path)
    assert not (tmp_path / "pyvenv.cfg").exists()
    assert not fake_lib.exists()
    assert any("pyvenv.cfg" in item for item in removed)


def test_python_starts_false_for_missing_binary(tmp_path: Path) -> None:
    assert windows_launch.python_starts(tmp_path / "missing-python.exe") is False
