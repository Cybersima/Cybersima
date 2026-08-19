import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ensure_venv import write_pyvenv_cfg


def test_write_pyvenv_cfg_sets_home_to_real_python(tmp_path: Path) -> None:
    write_pyvenv_cfg(tmp_path, home=r"C:\Python312", executable=r"C:\Python312\python.exe", version="3.12.10")
    text = (tmp_path / "pyvenv.cfg").read_text(encoding="utf-8")
    assert "home = C:\\Python312" in text
    assert "include-system-site-packages = false" in text
    assert "executable = C:\\Python312\\python.exe" in text
