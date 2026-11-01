"""Reference-data checks for physiology.py's drain rates: tuned numbers, unlike
test_physiology.py's property tests, so these are expected to change when the rates are retuned.

Rough real ultrarunning ranges they pin: an unfed runner bonks after ~1-1.5h flat out and
~2-3.5h at a steady effort; fluid loss runs ~0.3 L/h in the cold to well over 1 L/h in heat.
"""

from sim.physiology import (
    GLYCOGEN_DRAIN_PCT_PER_HR_PER_EFFORT,
    is_bonking,
    step_glycogen,
    step_hydration,
)

TICK_MIN = 0.5


def _minutes_until_bonk(effort: int) -> float:
    glycogen, minutes = 100.0, 0.0
    while not is_bonking(glycogen):
        glycogen = step_glycogen(glycogen, effort, TICK_MIN, ate=False)
        minutes += TICK_MIN
    return minutes


def _hydration_after(hours: float, heat: int) -> float:
    hydration = 100.0
    for _ in range(int(hours * 60 / TICK_MIN)):
        hydration = step_hydration(hydration, heat, TICK_MIN, drank=False)
    return hydration


def test_unfed_runner_bonks_in_realistic_time():
    assert 60 <= _minutes_until_bonk(effort=10) <= 90
    assert 120 <= _minutes_until_bonk(effort=5) <= 210
    assert _minutes_until_bonk(effort=2) >= 6 * 60  # a slow hike barely touches glycogen


def test_one_feed_buys_roughly_half_an_hour_at_steady_effort():
    refill = step_glycogen(50.0, 5, TICK_MIN, ate=True) - step_glycogen(
        50.0, 5, TICK_MIN, ate=False
    )
    minutes_of_running = refill / (5 * GLYCOGEN_DRAIN_PCT_PER_HR_PER_EFFORT) * 60
    assert 20 <= minutes_of_running <= 40


def test_dehydration_is_faster_in_heat():
    assert 60 <= _hydration_after(hours=3, heat=0) <= 80  # cold: slow loss
    assert _hydration_after(hours=3, heat=5) <= 50  # warm: half gone in 3h
    assert _hydration_after(hours=3, heat=5) > 0  # but not bone dry yet
