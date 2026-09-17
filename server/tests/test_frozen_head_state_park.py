"""Property tests focused on tick() — it composes every stepper, so running it across many
seeds and many ticks in sequence surfaces gaps (bad dict keys, out-of-range values, stuck
state) without needing a separate test per stepper.
"""

import random

from hypothesis import given
from hypothesis import strategies as st

from sim.frozen_head_state_park import WEATHER_CONDITIONS, initial_state, tick

seeds = st.integers(min_value=0, max_value=2**32 - 1)
start_hours = st.floats(min_value=0, max_value=24, allow_nan=False)
dt_mins = st.floats(min_value=1, max_value=60, allow_nan=False)
num_ticks = st.integers(min_value=1, max_value=200)


@given(seeds, start_hours, dt_mins, num_ticks)
def test_tick_sequence_stays_valid(seed, start_hour, dt_min, num_ticks):
    rng = random.Random(seed)
    state = initial_state(start_hour=start_hour, rng=rng)
    prev_elapsed = state.elapsed_min

    for _ in range(num_ticks):
        state = tick(state, dt_min=dt_min, start_hour=start_hour, rng=rng)

        assert state.weather in WEATHER_CONDITIONS
        assert 0.0 <= state.fog_pct <= 100.0
        assert state.heat_index >= 0
        assert state.temperature_c == state.temperature_c  # not NaN
        assert state.elapsed_min == prev_elapsed + dt_min
        prev_elapsed = state.elapsed_min


@given(start_hours)
def test_initial_state_works_without_an_rng(start_hour):
    state = initial_state(start_hour=start_hour)
    assert state.weather in WEATHER_CONDITIONS
