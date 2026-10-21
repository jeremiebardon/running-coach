import pytest

from running_coach.agent.tools import make_tools


@pytest.fixture
def tools(fixture_data, clock):
    return {t.name: t for t in make_tools(fixture_data, clock)}


def test_finds_todays_run_with_its_strides(tools):
    res = tools["get_activity_details"].invoke({"date": "2026-10-17"})
    assert res["activity"]["name"] == "Easy run + strides"
    assert res["activity"]["work_intervals"]["count"] == 6


def test_reports_best_efforts_including_the_half(tools):
    res = tools["get_best_efforts"].invoke({"days": 180})
    half = next(e for e in res if e["label"] == "half")
    assert half["summary"].startswith("half in 1:2")


def test_returns_an_error_value_not_a_raise_when_there_is_no_run_on_a_date(tools):
    assert "No run found" in tools["get_activity_details"].invoke({"date": "2026-10-16"})["error"]


def test_validates_arguments_against_the_schema(tools):
    with pytest.raises(ValueError):
        tools["build_pacing_plan"].invoke({"distance": "marathon", "target_time": "fast"})
