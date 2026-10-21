from running_coach.domain.pacing import build_pacing_plan
from running_coach.domain.time import parse_duration


def test_even_plan_sums_exactly_to_the_target():
    plan = build_pacing_plan(distance_m=42195, target_sec=10500, strategy="even")
    assert plan["splits"][-1]["cumulative"] == "2:55:00"
    assert plan["average_pace"] == "4:09/km"
    assert len(plan["splits"]) == 9  # 5,10,...,40 + finish


def test_negative_split_runs_the_second_half_faster_but_keeps_the_total():
    plan = build_pacing_plan(distance_m=42195, target_sec=10500, strategy="negative")
    first = parse_duration(plan["first_half_pace"].removesuffix("/km"))
    second = parse_duration(plan["second_half_pace"].removesuffix("/km"))
    assert first > second
    assert plan["splits"][-1]["cumulative"] == "2:55:00"
