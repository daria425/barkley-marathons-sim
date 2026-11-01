"""Property tests focused on tick() — it composes every stepper, so running it across many
weathers, start hours and many ticks in sequence surfaces gaps (bad dict keys, out-of-range
values, stuck state) without needing a separate test per stepper. No rng since ADR-0024: the
caller supplies the weather, and everything else is a pure function of it plus the clock.
"""

from hypothesis import given
from hypothesis import strategies as st

from sim.frozen_head_state_park import (
    compute_fog_pct,
    compute_temperature,
    conditions_at,
    initial_state,
    tick,
)
from sim.sim_constants import WEATHER_CONDITIONS, WEATHER_OFFSETS

weathers = st.sampled_from(WEATHER_CONDITIONS)
start_hours = st.floats(min_value=0, max_value=24, allow_nan=False)
dt_mins = st.floats(min_value=1, max_value=60, allow_nan=False)
num_ticks = st.integers(min_value=1, max_value=200)


@given(weathers, start_hours, dt_mins, num_ticks, st.data())
def test_tick_sequence_stays_valid(start_weather, start_hour, dt_min, num_ticks, data):
    state = initial_state(start_hour=start_hour, weather=start_weather)
    prev_elapsed = state.elapsed_min

    for _ in range(num_ticks):
        weather = data.draw(weathers)
        state = tick(state, dt_min=dt_min, start_hour=start_hour, weather=weather)

        assert state.weather == weather
        assert 0.0 <= state.fog_pct <= 100.0
        assert state.heat_index >= 0
        assert state.temperature_c == state.temperature_c  # not NaN
        assert state.elapsed_min == prev_elapsed + dt_min
        prev_elapsed = state.elapsed_min


@given(weathers, start_hours, st.floats(min_value=0, max_value=3600, allow_nan=False))
def test_conditions_are_a_pure_function_of_time_and_weather(weather, start_hour, elapsed_min):
    assert conditions_at(elapsed_min, start_hour, weather) == conditions_at(
        elapsed_min, start_hour, weather
    )


def test_temperature_has_no_jitter():
    """15:00 is the diurnal peak (20°C) — with the jitter gone, that's exact plus the offset."""
    for weather in WEATHER_CONDITIONS:
        assert compute_temperature(9 * 60, 6.0, weather) == 20 + WEATHER_OFFSETS[weather]


def test_fog_is_weather_plus_night_bump_exactly():
    assert compute_fog_pct("clear", is_daylight=True) == 0.0
    assert compute_fog_pct("clear", is_daylight=False) == 10.0
    assert compute_fog_pct("fog", is_daylight=True) == 50.0
    assert compute_fog_pct("fog", is_daylight=False) == 60.0
    assert compute_fog_pct("storm", is_daylight=True) == 20.0
