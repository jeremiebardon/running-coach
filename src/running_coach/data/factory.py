from running_coach.data.base import Clock, SystemClock, TrainingData
from running_coach.data.fixtures import DEFAULT_FIXTURE, FixtureData
from running_coach.data.intervals_icu import IntervalsIcu
from running_coach.settings import Settings


def build_data_source(settings: Settings, clock: Clock) -> TrainingData:
    if settings.data_source == "fixtures":
        return FixtureData(settings.fixture_path or DEFAULT_FIXTURE, clock)
    if not settings.intervals_api_key:
        raise RuntimeError("INTERVALS_API_KEY is missing (or set DATA_SOURCE=fixtures).")
    return IntervalsIcu(settings.intervals_api_key, settings.intervals_athlete_id)


def athlete_clock(settings: Settings) -> Clock:
    return SystemClock(settings.athlete_timezone)
