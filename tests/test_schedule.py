from datetime import datetime

from pulsearb.engine.schedule import format_hhmm, window_open


def test_overnight_window_wraps_midnight() -> None:
    assert window_open("22:00", "06:00", datetime(2026, 8, 21, 22, 0))
    assert window_open("22:00", "06:00", datetime(2026, 8, 21, 23, 59))
    assert window_open("22:00", "06:00", datetime(2026, 8, 22, 0, 0))
    assert window_open("22:00", "06:00", datetime(2026, 8, 22, 5, 59))
    assert not window_open("22:00", "06:00", datetime(2026, 8, 22, 6, 0))
    assert not window_open("22:00", "06:00", datetime(2026, 8, 21, 21, 59))
    assert not window_open("22:00", "06:00", datetime(2026, 8, 21, 12, 0))


def test_same_start_and_stop_is_all_day() -> None:
    assert window_open("00:00", "00:00", datetime(2026, 8, 21, 12, 0))
    assert window_open("10:00", "10:00", datetime(2026, 8, 21, 3, 0))


def test_daytime_window() -> None:
    assert window_open("09:00", "17:00", datetime(2026, 8, 21, 9, 0))
    assert window_open("09:00", "17:00", datetime(2026, 8, 21, 16, 59))
    assert not window_open("09:00", "17:00", datetime(2026, 8, 21, 17, 0))
    assert not window_open("09:00", "17:00", datetime(2026, 8, 21, 8, 59))


def test_format_hhmm_clamps() -> None:
    assert format_hhmm("22:00") == "22:00"
    assert format_hhmm("9:5") == "09:05"
    assert format_hhmm("nope", "22:00") == "22:00"
