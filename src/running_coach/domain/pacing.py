from typing import Literal

from running_coach.domain.time import format_duration, format_pace, js_round

type PacingStrategy = Literal["even", "negative"]


def build_pacing_plan(
    *,
    distance_m: float,
    target_sec: float,
    strategy: PacingStrategy,
    split_every_km: float = 5,
    swing_pct: float = 2,
) -> dict:
    """Even or negative-split plan.

    For "negative", the first half is run `swing_pct`/2 slower and the second half
    `swing_pct`/2 faster than average, so the total still equals the target exactly.
    """
    swing = swing_pct / 100 if strategy == "negative" else 0
    total_km = distance_m / 1000
    half = total_km / 2
    avg = target_sec / total_km
    p1 = avg * (1 + swing / 2)
    p2 = avg * (1 - swing / 2)

    def time_at(km: float) -> float:
        return km * p1 if km <= half else half * p1 + (km - half) * p2

    marks: list[float] = []
    km = split_every_km
    while km < total_km - 1e-9:
        marks.append(km)
        km += split_every_km
    marks.append(total_km)

    splits = []
    prev_km = 0.0
    for km in marks:
        split = time_at(km) - time_at(prev_km)
        splits.append(
            {
                "at_km": js_round(km * 1000) / 1000,
                "split_time": format_duration(split),
                "cumulative": format_duration(time_at(km)),
                "pace": format_pace(split / (km - prev_km)),
            }
        )
        prev_km = km

    return {
        "strategy": strategy,
        "target": format_duration(target_sec),
        "average_pace": format_pace(avg),
        "first_half_pace": format_pace(p1),
        "second_half_pace": format_pace(p2),
        "splits": splits,
    }
