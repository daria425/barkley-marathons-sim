"""Property tests: general direction of behavior, not tuned numbers.

If you retune a formula's constants, these should keep passing unchanged.
"""

from hypothesis import given
from hypothesis import strategies as st

from sim.physiology import (
    BONK_GLYCOGEN_PCT,
    BONK_PUSH_EFFORT_THRESHOLD,
    BONK_PUSH_LIMIT_MIN,
    compute_pace,
    has_collapsed,
    initial_state,
    is_bonking,
    step_bonk_push,
    step_core_temp,
    step_glycogen,
    step_heart_rate,
    step_hydration,
    tick,
)

effort = st.integers(min_value=1, max_value=10)
heat = st.integers(min_value=0, max_value=10)
dt_min = st.floats(min_value=1, max_value=180, allow_nan=False)
pct = st.floats(min_value=0, max_value=100, allow_nan=False)
base_hr = st.integers(min_value=40, max_value=100)
elapsed_min = st.floats(min_value=0, max_value=60 * 60, allow_nan=False)
core_temp_c = st.floats(min_value=35, max_value=42, allow_nan=False)
pace = st.floats(min_value=3, max_value=15, allow_nan=False)


def bump(value, cap=10):
    return min(value + 1, cap)


@given(base_hr, effort, heat, elapsed_min)
def test_heart_rate_rises_with_effort(base_hr, effort, heat, elapsed_min):
    lo = step_heart_rate(base_hr, effort, heat, elapsed_min)
    hi = step_heart_rate(base_hr, bump(effort), heat, elapsed_min)
    assert hi >= lo


@given(base_hr, effort, heat, elapsed_min)
def test_heart_rate_rises_with_heat(base_hr, effort, heat, elapsed_min):
    lo = step_heart_rate(base_hr, effort, heat, elapsed_min)
    hi = step_heart_rate(base_hr, effort, bump(heat), elapsed_min)
    assert hi >= lo


@given(pct, effort, dt_min)
def test_glycogen_never_negative(pct, effort, dt_min):
    assert step_glycogen(pct, effort, dt_min, ate=False) >= 0


@given(pct, effort, dt_min)
def test_glycogen_depletes_with_effort(pct, effort, dt_min):
    lo_effort = step_glycogen(pct, effort, dt_min, ate=False)
    hi_effort = step_glycogen(pct, bump(effort), dt_min, ate=False)
    assert hi_effort <= lo_effort


@given(pct, effort, dt_min)
def test_eating_refills_glycogen(pct, effort, dt_min):
    without = step_glycogen(pct, effort, dt_min, ate=False)
    with_food = step_glycogen(pct, effort, dt_min, ate=True)
    assert with_food >= without


@given(pct, heat, dt_min)
def test_hydration_never_negative(pct, heat, dt_min):
    assert step_hydration(pct, heat, dt_min, drank=False) >= 0


@given(pct, heat, dt_min)
def test_hydration_depletes_with_heat(pct, heat, dt_min):
    lo_heat = step_hydration(pct, heat, dt_min, drank=False)
    hi_heat = step_hydration(pct, bump(heat), dt_min, drank=False)
    assert hi_heat <= lo_heat


@given(pct, heat, dt_min)
def test_drinking_refills_hydration(pct, heat, dt_min):
    without = step_hydration(pct, heat, dt_min, drank=False)
    with_drink = step_hydration(pct, heat, dt_min, drank=True)
    assert with_drink >= without


@given(core_temp_c, core_temp_c, effort, heat, dt_min)
def test_core_temp_rises_with_more_effort(start_temp, core_temp, effort, heat, dt_min):
    lo = step_core_temp(start_temp, core_temp, effort, heat, dt_min)
    hi = step_core_temp(start_temp, core_temp, bump(effort), heat, dt_min)
    assert hi >= lo


@given(core_temp_c, core_temp_c, effort, heat, dt_min)
def test_core_temp_rises_with_more_heat(start_temp, core_temp, effort, heat, dt_min):
    lo = step_core_temp(start_temp, core_temp, effort, heat, dt_min)
    hi = step_core_temp(start_temp, core_temp, effort, bump(heat), dt_min)
    assert hi >= lo


@given(pct)
def test_bonking_below_threshold(pct):
    assert is_bonking(pct) == (pct < BONK_GLYCOGEN_PCT)


@given(pace, effort)
def test_bonking_collapses_pace(pace, effort):
    normal = compute_pace(pace, effort, glycogen_pct=100.0)
    bonking = compute_pace(pace, effort, glycogen_pct=BONK_GLYCOGEN_PCT - 1)
    assert bonking >= normal


@given(pace, effort)
def test_pace_faster_with_more_effort(pace, effort):
    lo_effort_pace = compute_pace(pace, effort, glycogen_pct=100.0)
    hi_effort_pace = compute_pace(pace, bump(effort), glycogen_pct=100.0)
    assert hi_effort_pace <= lo_effort_pace


@given(effort, heat, dt_min)
def test_tick_advances_elapsed_time(effort, heat, dt_min):
    state = initial_state()
    next_state = tick(state, base_hr=140, effort_rpe=effort, heat=heat, dt_min=dt_min)
    assert next_state.elapsed_min == state.elapsed_min + dt_min


@given(effort, heat, dt_min)
def test_tick_never_produces_invalid_glycogen_or_hydration(effort, heat, dt_min):
    state = initial_state()
    next_state = tick(state, base_hr=140, effort_rpe=effort, heat=heat, dt_min=dt_min)
    assert 0 <= next_state.glycogen_pct <= 100
    assert 0 <= next_state.hydration_pct <= 100


@given(dt_min)
def test_bonk_push_accumulates_while_pushing_through_a_bonk(dt_min):
    result = step_bonk_push(
        bonk_push_min=0.0,
        glycogen_pct=BONK_GLYCOGEN_PCT - 1,
        effort_rpe=BONK_PUSH_EFFORT_THRESHOLD,
        dt_min=dt_min,
    )
    assert result > 0


@given(pct, effort, dt_min)
def test_bonk_push_resets_once_not_bonking(pct, effort, dt_min):
    result = step_bonk_push(
        bonk_push_min=50.0,
        glycogen_pct=BONK_GLYCOGEN_PCT,  # right at the edge, not bonking
        effort_rpe=effort,
        dt_min=dt_min,
    )
    assert result == 0


@given(pct, dt_min)
def test_bonk_push_resets_once_effort_drops(pct, dt_min):
    result = step_bonk_push(
        bonk_push_min=50.0,
        glycogen_pct=BONK_GLYCOGEN_PCT - 1,
        effort_rpe=BONK_PUSH_EFFORT_THRESHOLD - 1,
        dt_min=dt_min,
    )
    assert result == 0


def test_has_collapsed_crosses_the_limit():
    assert not has_collapsed(BONK_PUSH_LIMIT_MIN - 1)
    assert has_collapsed(BONK_PUSH_LIMIT_MIN)


@given(pace, effort)
def test_collapse_overrides_the_bonk_floor(pace, effort):
    bonk_glycogen = BONK_GLYCOGEN_PCT - 1
    gritting_it_out = compute_pace(pace, effort, glycogen_pct=bonk_glycogen, collapsed=False)
    collapsed = compute_pace(pace, effort, glycogen_pct=bonk_glycogen, collapsed=True)
    assert collapsed > gritting_it_out
