"""Generate fixtures/athlete-sub3.json — a synthetic ~16-week block for a runner
around 70 km/week, with a 1:24 half 6 days ago and two recent 10ks.

Output is in the raw intervals.icu shape (see running_coach/data/fixtures.py).
Deterministic (seeded LCG, same sequence as the original TypeScript generator),
so the committed file is reproducible:  uv run python scripts/generate_fixture.py

Later: replace with a `record_fixture` script that pulls YOUR real data and
anonymises it — that's how you grow a realistic golden dataset.
"""

import json
import math
from datetime import date, timedelta
from pathlib import Path

ANCHOR = date(2026, 10, 17)  # a Saturday; offsets are relative to it
DAYS = 16 * 7
OUT = Path(__file__).resolve().parents[1] / "fixtures" / "athlete-sub3.json"

_seed = 42


def rand() -> float:
    global _seed
    _seed = (_seed * 1664525 + 1013904223) % 2**32
    return _seed / 2**32


def jitter(n: float, pct: float) -> float:
    return n * (1 + (rand() * 2 - 1) * pct)


def js_round(x: float) -> int:
    return math.floor(x + 0.5)


def round1(x: float) -> float | int:
    """Math.round(x * 10) / 10, printed like JavaScript (3, not 3.0)."""
    v = js_round(x * 10) / 10
    return int(v) if v.is_integer() else v


activities: list[dict] = []
load_by_offset: dict[int, int] = {}
next_id = 1_000_000


def run(o: int, name: str, km: float, pace_sec: float, hr: float, intensity: float, extra: dict | None = None) -> None:
    global next_id
    moving = js_round(km * pace_sec)
    load = js_round(moving / 3600 * intensity * intensity * 100)
    load_by_offset[o] = load_by_offset.get(o, 0) + load
    activities.append(
        {
            "_dayOffset": o,
            "_time": "07:15:00",
            "id": f"i{next_id}",
            "name": name,
            "type": "Run",
            "distance": js_round(km * 1000),
            "moving_time": moving,
            "elapsed_time": moving + 60,
            "average_heartrate": js_round(hr),
            "max_heartrate": js_round(hr + 12),
            "total_elevation_gain": js_round(jitter(km * 4, 0.4)),
            "icu_training_load": load,
            **(extra or {}),
        }
    )
    next_id += 1


def reps(n: int, rep_m: float, rep_pace: float, rec_m: float, rec_pace: float, hr: float) -> list[dict]:
    out = []
    for i in range(n):
        out.append(
            {
                "label": f"Rep {i + 1}",
                "type": "WORK",
                "distance": rep_m,
                "moving_time": js_round(jitter(rep_m / 1000 * rep_pace, 0.012)),
                "average_heartrate": js_round(jitter(hr, 0.01)),
            }
        )
        if i < n - 1:
            out.append(
                {
                    "type": "RECOVERY",
                    "distance": rec_m,
                    "moving_time": js_round(rec_m / 1000 * rec_pace),
                    "average_heartrate": js_round(hr - 25),
                }
            )
    return out


for o in range(-DAYS + 1, 1):
    dow = ((ANCHOR + timedelta(days=o)).weekday() + 1) % 7  # 0 Sun .. 6 Sat, like JS getUTCDay()

    # ---- special days (races, taper, recovery) ----
    if o == -39:
        run(o, "10K race", 10.02, 239, 178, 1.02, {"race": True})
        continue
    if o == -34:
        run(o, "10K race - PB", 10.0, 235.5, 180, 1.03, {"race": True})
        continue
    if o == -6:
        run(o, "Half marathon race", 21.1, 238.9, 176, 1.0, {"race": True})
        continue
    if o > -6:
        if o == -4:
            run(o, "Recovery jog", 7.0, 320, 132, 0.68)
        if o == -2:
            run(o, "Easy run", 9.0, 310, 136, 0.7)
        if o == 0:
            run(o, "Easy run + strides", 10.2, 305, 139, 0.72, {"icu_intervals": reps(6, 100, 200, 100, 330, 160)})
        continue
    taper = o > -13  # week before the half
    scale = 0.6 if taper else 1

    match dow:
        case 1:  # Monday rest
            pass
        case 2:  # VMA
            n = 4 if taper else 6
            run(o, f"VMA {n}x1000m", 12 * scale + 2, 290, 152, 0.9,
                {"icu_intervals": reps(n, 1000, jitter(216, 0.01), 400, 360, 172)})  # fmt: skip
        case 3:
            run(o, "Easy run", jitter(11 * scale, 0.1), jitter(305, 0.02), jitter(140, 0.02), 0.72)
        case 4:  # threshold
            n = 2 if taper else 3
            run(o, f"Threshold {n}x3km", n * 3 + 5, 268, 158, 0.88,
                {"icu_intervals": reps(n, 3000, jitter(238, 0.008), 600, 340, 167)})  # fmt: skip
        case 5:
            run(o, "Easy run", jitter(8 * scale, 0.1), jitter(310, 0.02), jitter(138, 0.02), 0.7)
        case 6:
            run(o, "Progression run", jitter(12 * scale, 0.05), jitter(280, 0.02), 148, 0.8)
        case 0:  # long run, building 20 -> 28 km
            km = 14 if taper else min(28, 20 + (o + DAYS) // 14)
            run(o, "Long run", km, jitter(292, 0.015), 145, 0.76)

# ---- wellness: CTL/ATL as 42/7-day exponentially weighted load ----
wellness: list[dict] = []
ctl, atl = 48.0, 52.0
ctl_history: list[float] = []
for o in range(-DAYS + 1, 1):
    load = load_by_offset.get(o, 0)
    ctl += (load - ctl) / 42
    atl += (load - atl) / 7
    ctl_history.append(ctl)
    week_ago = ctl_history[-8] if len(ctl_history) >= 8 else ctl_history[0]
    wellness.append(
        {
            "_dayOffset": o,
            "ctl": round1(ctl),
            "atl": round1(atl),
            "rampRate": round1(ctl - week_ago),  # CTL change over 7 days
            "restingHR": js_round(jitter(46, 0.04)),
            "hrv": js_round(jitter(72, 0.1)),
            "sleepSecs": js_round(jitter(7.4 * 3600, 0.08)),
        }
    )

fixture = {
    "athlete": {
        "id": "i000000",
        "name": "Demo Athlete",
        "sportSettings": [
            {"types": ["Run", "TrailRun", "VirtualRun"], "threshold_pace": 1000 / 240, "lthr": 171, "max_hr": 192}
        ],
    },
    "activities": activities,
    "wellness": wellness,
}

if __name__ == "__main__":
    OUT.write_text(json.dumps(fixture, indent=1, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    print(f"wrote {len(activities)} activities, {len(wellness)} wellness days")
