"""Training volume, fitness/form and best efforts — all pure functions over domain types."""

from dataclasses import dataclass
from typing import Literal

from running_coach.domain.models import Activity, IsoDate, Performance, WellnessDay, is_run
from running_coach.domain.time import (
    RACE_DISTANCES,
    add_days,
    format_duration,
    format_pace,
    js_round,
    pace_sec_per_km,
    round1,
    week_start,
)

# ------------------------------- volume -------------------------------


@dataclass(slots=True)
class WeekVolume:
    week_start: IsoDate
    km: float = 0
    runs: int = 0
    longest_run_km: float = 0
    moving_hours: float = 0


def weekly_volume(activities: list[Activity], today: IsoDate, weeks: int) -> list[WeekVolume]:
    """Weekly running volume for the `weeks` weeks ending with the week of `today`."""
    first_week = add_days(week_start(today), -7 * (weeks - 1))
    buckets = {ws: WeekVolume(ws) for ws in (add_days(first_week, 7 * i) for i in range(weeks))}
    for a in filter(is_run, activities):
        bucket = buckets.get(week_start(a.date))
        if bucket is None:
            continue
        km = a.distance_m / 1000
        bucket.km += km
        bucket.runs += 1
        bucket.longest_run_km = max(bucket.longest_run_km, km)
        bucket.moving_hours += a.moving_time_sec / 3600
    return [
        WeekVolume(w.week_start, round1(w.km), w.runs, round1(w.longest_run_km), round1(w.moving_hours))
        for w in buckets.values()
    ]


@dataclass(frozen=True, slots=True)
class TrainingContext:
    avg_weekly_km: float
    """average over COMPLETED weeks (the current partial week is excluded)"""
    longest_run_km: float
    weeks_considered: int


def training_context(activities: list[Activity], today: IsoDate, weeks: int = 8) -> TrainingContext:
    all_weeks = weekly_volume(activities, today, weeks + 1)
    completed = all_weeks[:-1]
    avg = sum(w.km for w in completed) / max(len(completed), 1)
    return TrainingContext(
        avg_weekly_km=round1(avg),
        longest_run_km=max([0, *(w.longest_run_km for w in all_weeks)]),
        weeks_considered=len(completed),
    )


# ---------------------------- fitness / form ----------------------------

type FormZone = Literal["transition", "fresh", "grey-zone", "optimal-training", "high-risk"]


def form_zone(form_pct: float) -> FormZone:
    """Approximation of intervals.icu's form zones, expressed as TSB/CTL %."""
    if form_pct > 20:
        return "transition"
    if form_pct > 5:
        return "fresh"
    if form_pct > -10:
        return "grey-zone"
    if form_pct > -30:
        return "optimal-training"
    return "high-risk"


@dataclass(frozen=True, slots=True)
class FitnessSnapshot:
    date: IsoDate
    ctl: float
    atl: float
    tsb: float
    form_pct: int
    """TSB as a % of CTL — the scale intervals.icu uses for its form zones"""
    zone: FormZone
    ramp_rate: float | None = None


def fitness_snapshot(day: WellnessDay) -> FitnessSnapshot | None:
    if day.ctl is None or day.atl is None:
        return None
    tsb = day.ctl - day.atl
    form_pct = tsb / day.ctl * 100 if day.ctl > 0 else 0
    return FitnessSnapshot(
        date=day.date,
        ctl=round1(day.ctl),
        atl=round1(day.atl),
        tsb=round1(tsb),
        form_pct=js_round(form_pct),
        zone=form_zone(form_pct),
        ramp_rate=None if day.ramp_rate is None else round1(day.ramp_rate),
    )


# ----------------------------- best efforts -----------------------------


def best_efforts(activities: list[Activity]) -> list[Performance]:
    """Whole-activity best efforts at standard distances (±3%).

    POC simplification: intervals.icu exposes full pace curves (best 5k/10k
    *inside* any run), which would be strictly better — swap this for the
    pace-curve endpoint once you've confirmed its shape in the Swagger docs.
    """
    out: list[Performance] = []
    runs = [a for a in activities if is_run(a)]
    for label, distance_m in RACE_DISTANCES.items():
        candidates = sorted(
            # normalise to the exact distance at the run's average pace
            (
                (a, a.moving_time_sec * (distance_m / a.distance_m))
                for a in runs
                if abs(a.distance_m - distance_m) / distance_m <= 0.03
            ),
            key=lambda c: c[1],
        )
        if candidates:
            a, normalised_sec = candidates[0]
            out.append(Performance(label, distance_m, js_round(normalised_sec), a.date, a.id))
    return out


def describe_performance(p: Performance) -> str:
    return f"{p.label} in {format_duration(p.time_sec)} on {p.date}"


# --------------------------- activity summary ---------------------------


def summarise_activity(a: Activity, *, with_intervals: bool = True) -> dict:
    """Token-cheap view of an activity — the agent never sees raw API payloads."""
    summary = {
        "id": a.id,
        "name": a.name,
        "type": a.type,
        "date": a.date,
        "distance_km": js_round(a.distance_m / 10) / 100,
        "moving_time": format_duration(a.moving_time_sec),
        "avg_pace": format_pace(pace_sec_per_km(a.distance_m, a.moving_time_sec)) if a.distance_m > 0 else "n/a",
        "avg_hr": a.avg_hr,
        "max_hr": a.max_hr,
        "elevation_gain_m": a.elevation_gain_m,
        "training_load": a.training_load,
        "is_race": a.is_race,
    }
    work = [i for i in a.intervals if (i.kind or "").upper() == "WORK" and i.distance_m > 0]
    if with_intervals and work:
        dist = sum(i.distance_m for i in work)
        time = sum(i.moving_time_sec for i in work)
        hrs = [i.avg_hr for i in work if i.avg_hr is not None]
        summary["work_intervals"] = {
            "count": len(work),
            "avg_pace": format_pace(pace_sec_per_km(dist, time)),
            "avg_hr": js_round(sum(hrs) / len(hrs)) if hrs else None,
            "paces": [format_pace(pace_sec_per_km(i.distance_m, i.moving_time_sec)) for i in work],
        }
    return {k: v for k, v in summary.items() if v is not None}
