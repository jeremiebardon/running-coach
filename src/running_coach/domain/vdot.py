"""Jack Daniels / Jimmy Gilbert "VDOT" model.

VDOT = VO2 cost of running at velocity v / fraction of VO2max sustainable for t.
Unlike Riegel (a single power law), it encodes that the sustainable fraction of
VO2max decays with duration, which is why it tends to be more realistic for
extrapolating a 10k to a marathon.
"""

import math


def _vo2_at_velocity(v: float) -> float:
    """Oxygen cost (ml/kg/min) of running at v metres per minute."""
    return -4.6 + 0.182258 * v + 0.000104 * v * v


def _sustainable_fraction(t_min: float) -> float:
    """Fraction of VO2max sustainable for t minutes."""
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot_from_performance(distance_m: float, time_sec: float) -> float:
    t_min = time_sec / 60
    v = distance_m / t_min
    return _vo2_at_velocity(v) / _sustainable_fraction(t_min)


def predict_time_from_vdot(vdot: float, distance_m: float) -> float:
    """Inverse problem: the race time at `distance_m` that corresponds to `vdot`.

    VDOT is strictly decreasing in time for a fixed distance, so bisection is
    simple and robust (no derivative needed).
    """
    fast = distance_m / 450 * 60  # 450 m/min ≈ 2:13/km, faster than any human
    slow = distance_m / 80 * 60  # 80 m/min ≈ 12:30/km
    for _ in range(80):
        mid = (fast + slow) / 2
        if vdot_from_performance(distance_m, mid) > vdot:
            fast = mid
        else:
            slow = mid
    return (fast + slow) / 2


def riegel(time_sec: float, from_m: float, to_m: float, exponent: float = 1.06) -> float:
    """Peter Riegel's power law T2 = T1 · (D2/D1)^k, k ≈ 1.06."""
    return time_sec * (to_m / from_m) ** exponent
