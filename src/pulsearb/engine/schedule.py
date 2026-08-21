from __future__ import annotations

from datetime import datetime


def parse_hhmm(value: str, fallback: str = "00:00") -> tuple[int, int]:
    text = str(value or fallback).strip()
    try:
        hour_s, minute_s = text.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s[:2])
    except (TypeError, ValueError):
        hour_s, minute_s = fallback.split(":", 1)
        hour = int(hour_s)
        minute = int(minute_s)
    hour = max(0, min(23, hour))
    minute = max(0, min(59, minute))
    return hour, minute


def minutes_since_midnight(value: str, fallback: str = "00:00") -> int:
    hour, minute = parse_hhmm(value, fallback)
    return hour * 60 + minute


def window_open(start: str, stop: str, now: datetime | None = None) -> bool:
    """True when local time is inside [start, stop). Start==stop means all day.

    Overnight windows wrap midnight: 22:00–06:00 is 10pm through 6am.
    """
    clock = now or datetime.now()
    current = clock.hour * 60 + clock.minute
    begin = minutes_since_midnight(start, "22:00")
    end = minutes_since_midnight(stop, "06:00")
    if begin == end:
        return True
    if begin < end:
        return begin <= current < end
    return current >= begin or current < end


def format_hhmm(value: str, fallback: str = "00:00") -> str:
    hour, minute = parse_hhmm(value, fallback)
    return f"{hour:02d}:{minute:02d}"
