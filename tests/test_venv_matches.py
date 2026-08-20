import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from venv_matches import matches, venv_home


def test_venv_home_reads_pyvenv_cfg(tmp_path: Path) -> None:
    cfg = tmp_path / "pyvenv.cfg"
    cfg.write_text("home = C:\\Python314\ninclude-system-site-packages = false\n", encoding="utf-8")
    assert venv_home(cfg) == Path(r"C:\Python314")
    assert matches(cfg, Path(r"C:\Python314")) is True
    assert matches(cfg, Path(r"C:\Python312")) is False


def test_windows_launchers_pin_python314_not_py_dash_3() -> None:
    root = Path(__file__).resolve().parents[1]
    start = (root / "start.bat").read_text(encoding="utf-8")
    pick = (root / "scripts" / "pick-python.bat").read_text(encoding="utf-8")
    assert "setup-venv.bat" in start
    assert 'set "PY=py -3"' not in start
    assert "-E -m pulsearb" not in start
    assert "C:\\Python314\\python.exe" in pick
    assert "py -3.14" in pick
    assert 'set "PY=py -3"' not in pick
    assert (root / "python-path.txt.example").is_file()
