"""What the agent needs from the outside world, as Protocols.

Implementations: IntervalsIcu (live HTTP) and FixtureData (recorded payloads for
tests/evals). The agent tools only depend on these interfaces, which is what makes
evals deterministic.
"""

from datetime import datetime
from typing import Protocol
from zoneinfo import ZoneInfo

from running_coach.domain.models import Activity, AthleteProfile, DateRange, IsoDate, WellnessDay


class TrainingData(Protocol):
    def get_athlete_profile(self) -> AthleteProfile: ...
    def list_activities(self, range: DateRange) -> list[Activity]: ...
    def get_activity(self, id: str) -> Activity | None: ...
    def list_wellness(self, range: DateRange) -> list[WellnessDay]: ...


class Clock(Protocol):
    """ "What day is it for the athlete?" — injected so evals can freeze time."""

    def today(self) -> IsoDate: ...


class SystemClock:
    def __init__(self, timezone: str) -> None:
        self._tz = ZoneInfo(timezone)

    def today(self) -> IsoDate:
        return datetime.now(self._tz).date().isoformat()


class FixedClock:
    def __init__(self, date: IsoDate) -> None:
        self._date = date

    def today(self) -> IsoDate:
        return self._date
