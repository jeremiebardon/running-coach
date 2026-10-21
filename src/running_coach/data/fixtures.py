"""Recorded training data for tests, evals and demos.

Fixtures are stored in the RAW intervals.icu shape, with dates expressed as
offsets from "today" (`_dayOffset`). Two benefits:
 1. they go through the exact same mappers as live data (the ACL is tested too);
 2. they never go stale — "how was my run today?" always has a run today.
"""

import json
from pathlib import Path

from running_coach.data.base import Clock
from running_coach.data.schemas import (
    RawActivity,
    RawAthlete,
    RawWellness,
    to_activity,
    to_athlete_profile,
    to_wellness,
)
from running_coach.domain.models import Activity, AthleteProfile, DateRange, WellnessDay
from running_coach.domain.time import add_days

DEFAULT_FIXTURE = Path(__file__).resolve().parents[3] / "fixtures" / "athlete-sub3.json"


class FixtureData:
    def __init__(self, path: str | Path, clock: Clock) -> None:
        file = json.loads(Path(path).read_text(encoding="utf-8"))
        today = clock.today()
        self._athlete = to_athlete_profile(RawAthlete.model_validate(file["athlete"]))
        self._activities = [
            to_activity(RawActivity.model_validate(raw | {"start_date_local": f"{add_days(today, offset)}T{at}"}))
            for offset, at, raw in ((r.pop("_dayOffset"), r.pop("_time"), r) for r in file["activities"])
        ]
        self._wellness = [
            to_wellness(RawWellness.model_validate(raw | {"id": add_days(today, offset)}))
            for offset, raw in ((r.pop("_dayOffset"), r) for r in file["wellness"])
        ]

    def get_athlete_profile(self) -> AthleteProfile:
        return self._athlete

    def list_activities(self, range: DateRange) -> list[Activity]:
        return [a for a in self._activities if range.contains(a.date)]

    def get_activity(self, id: str) -> Activity | None:
        return next((a for a in self._activities if a.id == id), None)

    def list_wellness(self, range: DateRange) -> list[WellnessDay]:
        return [w for w in self._wellness if range.contains(w.date)]
