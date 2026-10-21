import pytest

from running_coach.domain.vdot import predict_time_from_vdot, riegel, vdot_from_performance


def test_matches_published_vdot_tables_within_tolerance():
    # Daniels' tables: VDOT 50 ≈ 19:57 5k / 3:10:49 marathon
    assert vdot_from_performance(5000, 19 * 60 + 57) == pytest.approx(50, abs=0.5)
    assert predict_time_from_vdot(50, 42195) / 60 == pytest.approx(190.8, abs=1.5)


def test_round_trips_performance_to_vdot_to_time():
    v = vdot_from_performance(21097.5, 5040)
    assert predict_time_from_vdot(v, 21097.5) == pytest.approx(5040, abs=0.5)


def test_riegel_doubles_a_half_into_about_2085x_for_a_marathon():
    assert riegel(5040, 21097.5, 42195) / 5040 == pytest.approx(2.085, abs=0.005)
