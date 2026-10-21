"""Lenient schemas for the intervals.icu payloads we use, plus raw -> domain mappers.

`extra="allow"` keeps unknown fields (the API returns ~100 per activity) and every
field is optional except ids, so an upstream addition never breaks parsing.
Field names verified against the official API docs / Swagger:
  https://intervals.icu/api/v1/docs/swagger-ui/index.html
"""

from typing import Annotated

from pydantic import BaseModel, BeforeValidator, ConfigDict

from running_coach.domain.models import Activity, AthleteProfile, Interval, WellnessDay
from running_coach.domain.time import js_round

# intervals.icu ids are strings ("i123") but some endpoints return numbers
type _Id = Annotated[str, BeforeValidator(str)]
# int | float so integer fields (HR, load) stay ints in tool output (139, not 139.0)
type _Num = int | float | None


class _Raw(BaseModel):
    model_config = ConfigDict(extra="allow")


class RawInterval(_Raw):
    label: str | None = None
    type: str | None = None
    distance: _Num = None
    moving_time: _Num = None
    average_heartrate: _Num = None


class RawActivity(_Raw):
    id: _Id
    name: str | None = None
    type: str | None = None
    start_date_local: str
    distance: _Num = None
    moving_time: _Num = None
    average_heartrate: _Num = None
    max_heartrate: _Num = None
    total_elevation_gain: _Num = None
    icu_training_load: _Num = None
    race: bool | None = None
    icu_intervals: list[RawInterval] | None = None


class RawWellness(_Raw):
    id: str  # the date, YYYY-MM-DD
    ctl: _Num = None
    atl: _Num = None
    rampRate: _Num = None  # camelCase = the API's field names
    restingHR: _Num = None
    hrv: _Num = None
    sleepSecs: _Num = None


class RawSportSettings(_Raw):
    types: list[str] | None = None
    threshold_pace: _Num = None  # metres / second
    lthr: _Num = None
    max_hr: _Num = None


class RawAthlete(_Raw):
    id: _Id
    name: str | None = None
    sportSettings: list[RawSportSettings] | None = None


# ------------------- anti-corruption layer: raw -> domain -------------------


def to_activity(raw: RawActivity) -> Activity:
    return Activity(
        id=raw.id,
        name=raw.name or "Untitled",
        type=raw.type or "Unknown",
        start_date_local=raw.start_date_local,
        distance_m=raw.distance or 0,
        moving_time_sec=raw.moving_time or 0,
        avg_hr=raw.average_heartrate,
        max_hr=raw.max_heartrate,
        elevation_gain_m=raw.total_elevation_gain,
        training_load=raw.icu_training_load,
        is_race=raw.race,
        intervals=[
            Interval(
                label=i.label,
                kind=i.type,
                distance_m=i.distance or 0,
                moving_time_sec=i.moving_time or 0,
                avg_hr=i.average_heartrate,
            )
            for i in raw.icu_intervals or []
        ],
    )


def to_wellness(raw: RawWellness) -> WellnessDay:
    return WellnessDay(
        date=raw.id,
        ctl=raw.ctl,
        atl=raw.atl,
        ramp_rate=raw.rampRate,
        resting_hr=raw.restingHR,
        hrv=raw.hrv,
        sleep_hours=None if raw.sleepSecs is None else js_round(raw.sleepSecs / 3600 * 10) / 10,
    )


def to_athlete_profile(raw: RawAthlete) -> AthleteProfile:
    run = next((s for s in raw.sportSettings or [] if "Run" in (s.types or [])), None)
    pace = run.threshold_pace if run else None
    return AthleteProfile(
        id=raw.id,
        name=raw.name,
        threshold_pace_sec_per_km=js_round(1000 / pace) if pace else None,
        lthr=run.lthr if run else None,
        max_hr=run.max_hr if run else None,
    )
