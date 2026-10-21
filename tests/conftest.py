import pytest

from running_coach.data.base import FixedClock
from running_coach.data.fixtures import DEFAULT_FIXTURE, FixtureData

TODAY = "2026-10-17"


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock(TODAY)


@pytest.fixture
def fixture_data(clock) -> FixtureData:
    return FixtureData(DEFAULT_FIXTURE, clock)
