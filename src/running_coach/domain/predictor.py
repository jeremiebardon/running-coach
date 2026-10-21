import math
from typing import Literal

from running_coach.domain.models import IsoDate, Performance
from running_coach.domain.time import days_between, format_duration, format_pace, js_round, pace_sec_per_km
from running_coach.domain.training import TrainingContext
from running_coach.domain.vdot import predict_time_from_vdot, riegel, vdot_from_performance

type Feasibility = Literal["likely", "borderline", "stretch", "unlikely"]


def _feasibility(gap_pct: float) -> Feasibility:
    if gap_pct >= 1:
        return "likely"
    if gap_pct >= -1:
        return "borderline"
    if gap_pct >= -3:
        return "stretch"
    return "unlikely"


def predict_race(
    *,
    performances: list[Performance],
    target_distance_m: float,
    context: TrainingContext,
    today: IsoDate,
    target_time_sec: float | None = None,
    race_date: IsoDate | None = None,
    max_reference_age_days: int = 120,
) -> dict:
    """Deterministic race prediction.

    The LLM never does this arithmetic — it calls this through a tool and
    *explains* the result. That split is the single most important design
    choice for groundedness. Returns `{"error": ...}` when there is no evidence.
    """
    candidates = [
        (p, days_between(p.date, today), vdot_from_performance(p.distance_m, p.time_sec)) for p in performances
    ]
    recent = sorted(
        (c for c in candidates if 0 <= c[1] <= max_reference_age_days),
        key=lambda c: c[2],
        reverse=True,
    )[:3]
    if not recent:
        return {"error": f"No race-like performance in the last {max_reference_age_days} days to base a prediction on."}

    # Of the top-3 VDOT efforts, prefer the one whose distance is closest
    # (log-scale) to the target: the most specific evidence wins.
    ref, ref_age, ref_vdot = min(recent, key=lambda c: abs(math.log(target_distance_m / c[0].distance_m)))

    centre = predict_time_from_vdot(ref_vdot, target_distance_m)
    adjustments: list[str] = []

    # Durability heuristics — VDOT assumes you are trained for the distance.
    if target_distance_m >= 21000:
        marathon = target_distance_m >= 40000
        vol = context.avg_weekly_km
        if marathon:
            vol_penalty = 0.04 if vol < 50 else 0.02 if vol < 70 else 0.005 if vol < 90 else 0
        else:
            vol_penalty = 0.02 if vol < 35 else 0.01 if vol < 50 else 0
        if vol_penalty > 0:
            centre *= 1 + vol_penalty
            adjustments.append(f"+{vol_penalty * 100:.1f}% for {vol:g} km/week average volume")
        long_needed = 30 if marathon else 18
        if context.longest_run_km < long_needed:
            centre *= 1.015
            adjustments.append(
                f"+1.5% because longest recent run is {context.longest_run_km:g} km (< {long_needed} km)"
            )

    fast_end = centre * 0.985
    slow_end = centre * 1.025  # asymmetric: more ways to go slower than faster

    prediction: dict = {
        "target_distance_km": target_distance_m / 1000,
        "reference": {
            "label": ref.label,
            "time": format_duration(ref.time_sec),
            "date": ref.date,
            "vdot": js_round(ref_vdot * 10) / 10,
            "age_days": ref_age,
        },
        "predicted": {
            "centre": format_duration(centre),
            "fast_end": format_duration(fast_end),
            "slow_end": format_duration(slow_end),
            "centre_sec": js_round(centre),
            "pace": format_pace(pace_sec_per_km(target_distance_m, centre)),
        },
        "riegel": format_duration(riegel(ref.time_sec, ref.distance_m, target_distance_m)),
        "adjustments": adjustments,
        "assumptions": [
            "Prediction reflects CURRENT fitness, not fitness after a future training block.",
            "Assumes a flat course, good weather and an even pacing strategy.",
            "Volume/long-run adjustments are coaching heuristics, not validated science.",
        ],
    }

    if target_time_sec is not None:
        gap_pct = (target_time_sec - centre) / centre * 100
        prediction["target"] = {
            "time": format_duration(target_time_sec),
            "required_pace": format_pace(pace_sec_per_km(target_distance_m, target_time_sec)),
            "gap_pct": js_round(gap_pct * 10) / 10,
            "feasibility": _feasibility(gap_pct),
        }
    if race_date:
        prediction["weeks_until_race"] = js_round(days_between(today, race_date) / 7 * 10) / 10
    return prediction
