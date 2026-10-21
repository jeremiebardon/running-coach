import pytest

from running_coach.domain.models import Performance
from running_coach.domain.predictor import predict_race
from running_coach.domain.training import TrainingContext

PERFORMANCES = [
    Performance("half", 21097.5, 5040, "2026-10-11", "a"),
    Performance("10k", 10000, 2355, "2026-09-13", "b"),
]


def predict(context: TrainingContext, **kwargs):
    defaults = {"performances": PERFORMANCES, "target_distance_m": 42195, "today": "2026-10-17"}
    return predict_race(context=context, **(defaults | kwargs))


def test_uses_the_closest_distance_reference_and_rates_a_sub_255_target():
    p = predict(TrainingContext(80, 28, 8), target_time_sec=10500)
    assert p["reference"]["label"] == "half"
    assert any("longest recent run" in a for a in p["adjustments"])
    assert p["target"]["feasibility"] in {"borderline", "stretch", "unlikely"}


def test_penalises_low_volume_for_the_marathon():
    high = predict(TrainingContext(95, 32, 8))
    low = predict(TrainingContext(40, 32, 8))
    assert low["predicted"]["centre_sec"] > high["predicted"]["centre_sec"] * 1.03


def test_returns_an_error_when_there_is_no_recent_performance():
    p = predict(TrainingContext(80, 30, 8), today="2027-12-01")
    assert "error" in p


@pytest.mark.parametrize("race_date", ["2027-01-16"])
def test_counts_weeks_until_race(race_date):
    assert predict(TrainingContext(80, 30, 8), race_date=race_date)["weeks_until_race"] == 13.0
