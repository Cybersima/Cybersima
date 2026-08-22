import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "packaging"))
from pick_python import usable


def test_regular_cpython_is_usable() -> None:
    assert usable((3, 12), r"C:\Python312\python.exe", "3.12.10")
    assert usable((3, 11), "/usr/bin/python3.11", "3.11.9")
    assert usable((3, 13), "python3.13", "3.13.2")
    assert usable((3, 14), r"C:\Python314\python.exe", "3.14.7 (tags/v3.14.7:xxxx, Aug  4 2026, 16:00:00) [MSC v.1944 64 bit (AMD64)]")


def test_free_threaded_314t_is_rejected() -> None:
    assert not usable((3, 14), r"C:\Python314\python3.14t.exe", "3.14.0 experimental free-threading")
    assert not usable((3, 14), r"C:\Python314\python3.14t.exe", "3.14.0")
    assert not usable((3, 11), "python3.11t", "3.11.9")


def test_old_python_is_rejected() -> None:
    assert not usable((3, 10), "python3.10", "3.10.14")
