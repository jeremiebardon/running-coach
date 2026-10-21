"""Durations, paces and calendar helpers (pure, date-only strings)."""

import math
from datetime import date, timedelta
from typing import Literal

from running_coach.domain.models import IsoDate

RACE_DISTANCES: dict[str, float] = {
    "5k": 5000,
    "10k": 10000,
    "half": 21097.5,
    "marathon": 42195,
}

type NamedDistance = Literal["5k", "10k", "half", "marathon"]


def js_round(x: float) -> int:
    """Round half up, like JavaScript's Math.round (Python's round() is banker's rounding)."""
    return math.floor(x + 0.5)


def round1(x: float) -> float:
    return js_round(x * 10) / 10


def resolve_distance_m(distance: str | float) -> float:
    """A named race distance, or a number of km."""
    if isinstance(distance, str):
        return RACE_DISTANCES[distance]
    return distance * 1000


def parse_duration(text: str) -> int:
    """Parse "2:55:00", "39:15" or "0:39:15" into seconds."""
    try:
        parts = [int(p) for p in text.strip().split(":")]
    except ValueError:
        parts = []
    if not 2 <= len(parts) <= 3 or any(n < 0 for n in parts):
        raise ValueError(f'Invalid duration "{text}" (expected h:mm:ss or mm:ss)')
    total = 0
    for n in parts:
        total = total * 60 + n
    return total


def format_duration(total_sec: float) -> str:
    s = js_round(total_sec)
    h, rem = divmod(s, 3600)
    m, sec = divmod(rem, 60)
    return f"{h}:{m:02d}:{sec:02d}" if h > 0 else f"{m}:{sec:02d}"


def format_pace(sec_per_km: float) -> str:
    return f"{format_duration(sec_per_km)}/km"


def pace_sec_per_km(distance_m: float, time_sec: float) -> float:
    return time_sec / (distance_m / 1000)


def add_days(d: IsoDate, days: int) -> IsoDate:
    return (date.fromisoformat(d) + timedelta(days=days)).isoformat()


def days_between(start: IsoDate, end: IsoDate) -> int:
    return (date.fromisoformat(end) - date.fromisoformat(start)).days


def week_start(d: IsoDate) -> IsoDate:
    """Monday of the ISO week containing `d`."""
    return add_days(d, -date.fromisoformat(d).weekday())
