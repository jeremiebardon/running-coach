import pytest

from running_coach.domain.dates import format_duration, js_round, parse_duration, week_start


def test_parses_and_formats_durations():
    assert parse_duration("2:55:00") == 10500
    assert parse_duration("39:15") == 2355
    assert format_duration(10500) == "2:55:00"
    assert format_duration(2355) == "39:15"
    with pytest.raises(ValueError):
        parse_duration("abc")


def test_finds_the_monday_of_a_week():
    assert week_start("2026-10-17") == "2026-10-12"  # Saturday -> Monday
    assert week_start("2026-10-12") == "2026-10-12"


def test_js_round_rounds_half_up_like_javascript():
    assert js_round(2.5) == 3  # Python's round(2.5) == 2
    assert js_round(-2.5) == -2
