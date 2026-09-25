"""Unit tests for sim/hallucinations.py (ADR-0017): severity curve, per-tick hallucination
rolls, and deterministic memory jumbling.
"""

from random import Random

from hypothesis import given
from hypothesis import strategies as st

from sim import hallucinations
from sim.sim_constants import HALLUCINATION_ONSET_MIN, HALLUCINATION_RAMP_MIN

elapsed_min = st.floats(min_value=0, max_value=60 * 60, allow_nan=False)


@given(elapsed_min)
def test_severity_is_zero_at_or_before_onset(elapsed_min):
    if elapsed_min <= HALLUCINATION_ONSET_MIN:
        assert hallucinations.severity(elapsed_min) == 0.0


@given(elapsed_min)
def test_severity_is_bounded_between_zero_and_one(elapsed_min):
    assert 0.0 <= hallucinations.severity(elapsed_min) <= 1.0


def test_severity_reaches_cap_at_ramp_and_beyond():
    assert hallucinations.severity(HALLUCINATION_RAMP_MIN) == 1.0
    assert hallucinations.severity(HALLUCINATION_RAMP_MIN * 10) == 1.0


def test_severity_is_monotonic_nondecreasing():
    points = [i * 5.0 for i in range(int(60 * 60 / 5))]
    values = [hallucinations.severity(p) for p in points]
    assert values == sorted(values)


def test_roll_never_fires_before_onset():
    rng = Random(1)
    for _ in range(2000):
        assert hallucinations.roll(HALLUCINATION_ONSET_MIN, rng) is None


def test_roll_is_deterministic_for_a_given_rng_state():
    rng_a = Random(9)
    rng_b = Random(9)
    results_a = [hallucinations.roll(HALLUCINATION_RAMP_MIN, rng_a) for _ in range(50)]
    results_b = [hallucinations.roll(HALLUCINATION_RAMP_MIN, rng_b) for _ in range(50)]
    assert results_a == results_b


def test_roll_eventually_fires_well_past_onset():
    rng = Random(42)
    results = [hallucinations.roll(HALLUCINATION_RAMP_MIN, rng) for _ in range(500)]
    assert any(r is not None for r in results)


def test_jumble_text_is_a_noop_at_zero_severity():
    text = 'From Day 1 to Day 2 (loop 3): found 2 book(s), felt strong. "all good"'
    assert hallucinations.jumble_text(text, 0.0) == text


def test_jumble_text_is_deterministic_for_the_same_input():
    text = 'From Day 1 to Day 2 (loop 3): found 2 book(s), felt strong throughout. "all good"'
    first = hallucinations.jumble_text(text, 0.6)
    second = hallucinations.jumble_text(text, 0.6)
    assert first == second


def test_jumble_text_actually_changes_the_text_at_high_severity():
    text = (
        "From Day 1 to Day 2 (loop 3): found 2 book(s), felt strong throughout, "
        'ate 3x and drank 4x. "all good out here, feeling fine"'
    )
    assert hallucinations.jumble_text(text, 1.0) != text


def test_jumble_severity_for_matches_severity_times_cap():
    for m in (0.0, 100.0, HALLUCINATION_RAMP_MIN, HALLUCINATION_RAMP_MIN * 2):
        expected = hallucinations.severity(m) * hallucinations.JUMBLE_MAX_SEVERITY
        assert hallucinations.jumble_severity_for(m) == expected
