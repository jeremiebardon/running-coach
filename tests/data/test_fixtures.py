from running_coach.domain.models import DateRange
from tests.conftest import TODAY


def test_fixture_dates_are_relative_to_the_clock(fixture_data):
    [today_run] = fixture_data.list_activities(DateRange(TODAY, TODAY))
    assert today_run.name == "Easy run + strides"
    assert today_run.start_date_local == f"{TODAY}T07:15:00"
    assert len([i for i in today_run.intervals if i.kind == "WORK"]) == 6


def test_fixture_profile_and_wellness_go_through_the_same_mappers(fixture_data):
    profile = fixture_data.get_athlete_profile()
    assert (profile.name, profile.threshold_pace_sec_per_km, profile.lthr) == ("Demo Athlete", 240, 171)
    [w] = fixture_data.list_wellness(DateRange(TODAY, TODAY))
    assert w.ctl is not None and w.sleep_hours is not None


def test_system_clock_resolves_iana_time_zones():
    # needs the tzdata package on Windows (no system zoneinfo database)
    from datetime import date

    from running_coach.data.base import SystemClock

    assert date.fromisoformat(SystemClock("America/Toronto").today())
