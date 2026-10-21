import pytest

from running_coach.domain.models import Activity, WellnessDay
from running_coach.domain.training import fitness_snapshot, form_zone, summarise_activity, weekly_volume


@pytest.mark.parametrize(
    ("pct", "zone"),
    [(25, "transition"), (10, "fresh"), (0, "grey-zone"), (-20, "optimal-training"), (-40, "high-risk")],
)
def test_form_zones(pct, zone):
    assert form_zone(pct) == zone


def test_fitness_snapshot_needs_ctl_and_atl():
    assert fitness_snapshot(WellnessDay("2026-10-17", ctl=50)) is None
    snap = fitness_snapshot(WellnessDay("2026-10-17", ctl=50, atl=60))
    assert (snap.tsb, snap.form_pct, snap.zone) == (-10, -20, "optimal-training")


def test_weekly_volume_buckets_runs_by_iso_week_and_ignores_rides():
    acts = [
        Activity("1", "Run", "Run", "2026-10-12T07:00:00", 10000, 3000),
        Activity("2", "Long", "Run", "2026-10-17T07:00:00", 20000, 6300),
        Activity("3", "Bike", "Ride", "2026-10-15T07:00:00", 40000, 4000),
        Activity("4", "Old", "Run", "2026-10-05T07:00:00", 8000, 2400),
    ]
    weeks = weekly_volume(acts, "2026-10-17", 2)
    assert [(w.week_start, w.km, w.runs, w.longest_run_km) for w in weeks] == [
        ("2026-10-05", 8.0, 1, 8.0),
        ("2026-10-12", 30.0, 2, 20.0),
    ]


def test_summary_drops_missing_fields():
    s = summarise_activity(Activity("1", "Easy", "Run", "2026-10-17T07:00:00", 10000, 3000))
    assert s == {
        "id": "1",
        "name": "Easy",
        "type": "Run",
        "date": "2026-10-17",
        "distance_km": 10.0,
        "moving_time": "50:00",
        "avg_pace": "5:00/km",
    }
