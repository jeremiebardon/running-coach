"""Domain model — the coach's own vocabulary.

Nothing here knows about intervals.icu, HTTP or LLMs. The data layer translates
external payloads INTO these types (anti-corruption layer), so if you later add
Garmin or Strava as a source, the domain and the agent tools don't move.
"""

from dataclasses import dataclass, field

type IsoDate = str  # YYYY-MM-DD (athlete local date)


@dataclass(frozen=True, slots=True)
class DateRange:
    oldest: IsoDate
    newest: IsoDate

    def contains(self, date: IsoDate) -> bool:
        return self.oldest <= date <= self.newest


@dataclass(slots=True)
class AthleteProfile:
    id: str
    name: str | None = None
    threshold_pace_sec_per_km: int | None = None
    """Running threshold pace in seconds per km, if configured in the source."""
    lthr: float | None = None
    max_hr: float | None = None


@dataclass(slots=True)
class Interval:
    distance_m: float
    moving_time_sec: float
    label: str | None = None
    kind: str | None = None
    """e.g. WORK / RECOVERY as reported by the source"""
    avg_hr: float | None = None


@dataclass(slots=True)
class Activity:
    id: str
    name: str
    type: str
    """Normalised sport type: "Run", "TrailRun", "VirtualRun", "Ride", ..."""
    start_date_local: str
    """Local start timestamp, ISO 8601 without zone"""
    distance_m: float
    moving_time_sec: float
    avg_hr: float | None = None
    max_hr: float | None = None
    elevation_gain_m: float | None = None
    training_load: float | None = None
    """Source training load (intervals.icu: icu_training_load)"""
    is_race: bool | None = None
    intervals: list[Interval] = field(default_factory=list)

    @property
    def date(self) -> IsoDate:
        return self.start_date_local[:10]


@dataclass(slots=True)
class WellnessDay:
    date: IsoDate
    ctl: float | None = None
    """Chronic training load ("fitness")"""
    atl: float | None = None
    """Acute training load ("fatigue")"""
    ramp_rate: float | None = None
    resting_hr: float | None = None
    hrv: float | None = None
    sleep_hours: float | None = None


@dataclass(frozen=True, slots=True)
class Performance:
    label: str
    distance_m: float
    time_sec: float
    date: IsoDate
    activity_id: str


RUN_TYPES = frozenset({"Run", "TrailRun", "VirtualRun"})


def is_run(a: Activity) -> bool:
    return a.type in RUN_TYPES
