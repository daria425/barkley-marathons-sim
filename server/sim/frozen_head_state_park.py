"""Representation of the state of the simulation world (Frozen Head State Park, Barkley location).

Terrain/elevation live in course.py instead — those are a function of where on the GPX
track the runner is, not of the weather. This file only knows about time and sky.

Randomness is always passed in as `rng: random.Random`, never called globally
(no bare `random.random()`), so callers can seed it and get reproducible ticks in tests.
"""

import random
from dataclasses import dataclass

from sim.sim_constants import TRANSITION_WEIGHTS, WEATHER_CONDITIONS, WEATHER_OFFSETS
from sim.sim_utils import calculate_hour, format_local_time


@dataclass(frozen=True)
class FrozenHeadStatePark:
    elapsed_min: float
    weather: str  # "clear" | "overcast" | "rain" | "storm" | "fog"
    temperature_c: float
    is_daylight: bool
    fog_pct: float  # 0-100, feeds navigation noise later
    heat_index: int  # 0-10, this is the `heat` param physiology already consumes
    local_time: str  # "Day 2, 3:15 AM ET" — frontend-facing, see format_local_time's docstring


def compute_is_daylight(elapsed_min: float, start_hour: float) -> bool:
    """Deterministic from time of day — no rng needed."""
    hour = calculate_hour(start_hour, elapsed_min)
    # 7am-7pm is daylight in Frozen Head State Park, around March - April
    return 7 <= hour < 19


def compute_temperature(
    elapsed_min: float, start_hour: float, weather: str, rng: random.Random
) -> float:
    """Diurnal curve (cooler at night, peak afternoon) + weather offset + small jitter."""
    hour = calculate_hour(start_hour, elapsed_min)
    # diurnal curve: peak at 15:00, low at 3:00
    diurnal_temp = -5 * (hour - 15) ** 2 / 36 + 20
    # if  there  is a key error thats our fuckery
    weather_offset = WEATHER_OFFSETS[weather]
    jitter = rng.uniform(-1, 1)
    return diurnal_temp + weather_offset + jitter


def step_weather(weather: str, rng: random.Random) -> str:
    """Weighted transition, biased toward staying the same condition — weather should read
    as a discrete event ('it's pouring') that then holds, not per-tick flicker.

    Weights are per-call, not scaled by dt_min — relies on the loop always ticking
    1 sim-minute at a time (CLAUDE.md). If dt_min ever varies, this needs rescaling.
    """
    weights = TRANSITION_WEIGHTS[weather]
    return rng.choices(list(weights), weights=list(weights.values()), k=1)[0]


def compute_fog_pct(weather: str, is_daylight: bool, rng: random.Random) -> float:
    """Mostly weather-driven (fog/storm raise it), with a night bump. Feeds navigation
    noise later — see CLAUDE.md's 'Comedy engine: true vs believed position'."""
    base = 0.0
    if weather == "fog":
        base += 50.0
    elif weather == "storm":
        base += 20.0
    if not is_daylight:
        base += 10.0
    jitter = rng.uniform(-5, 5)
    return min(100.0, max(0.0, base + jitter))


def compute_heat_index(temperature_c: float, weather: str) -> int:
    """Deterministic mapping to the 0-10 scale physiology's `heat` param already expects.
    This is the one seam where this file hands off to physiology.py."""
    if temperature_c < 10:
        return 0
    elif temperature_c < 15:
        return 1
    elif temperature_c < 20:
        return 2
    elif temperature_c < 25:
        return 3
    elif temperature_c < 30:
        return 4
    elif temperature_c < 35:
        return 5
    elif temperature_c < 40:
        return 6
    else:
        return 7 + (1 if weather == "storm" else 0) + (1 if weather == "fog" else 0)


def tick(
    state: FrozenHeadStatePark, dt_min: float, start_hour: float, rng: random.Random
) -> FrozenHeadStatePark:
    """Advance the park's conditions by one tick. This is the one function the sim loop calls."""
    elapsed_min = state.elapsed_min + dt_min
    weather = step_weather(state.weather, rng)
    is_daylight = compute_is_daylight(elapsed_min, start_hour)
    temperature_c = compute_temperature(elapsed_min, start_hour, weather, rng)
    fog_pct = compute_fog_pct(weather, is_daylight, rng)
    heat_index = compute_heat_index(temperature_c, weather)
    return FrozenHeadStatePark(
        elapsed_min=elapsed_min,
        weather=weather,
        temperature_c=temperature_c,
        is_daylight=is_daylight,
        fog_pct=fog_pct,
        heat_index=heat_index,
        local_time=format_local_time(start_hour, elapsed_min),
    )


def initial_state(start_hour: float = 6.0, rng: random.Random | None = None) -> FrozenHeadStatePark:
    """Race-start conditions. start_hour matters because Barkley's start time is unpredictable
    (horn blows any time midnight-noon) — never hardcode a sunrise assumption here."""
    rng = rng or random.Random()
    elapsed_time = 0.0
    start_weather = rng.choice(WEATHER_CONDITIONS)
    is_daylight = compute_is_daylight(elapsed_time, start_hour)
    temperature_c = compute_temperature(elapsed_time, start_hour, start_weather, rng)
    fog_pct = compute_fog_pct(start_weather, is_daylight, rng)
    heat_index = compute_heat_index(temperature_c, start_weather)
    return FrozenHeadStatePark(
        elapsed_min=elapsed_time,
        weather=start_weather,
        temperature_c=temperature_c,
        is_daylight=is_daylight,
        fog_pct=fog_pct,
        heat_index=heat_index,
        local_time=format_local_time(start_hour, elapsed_time),
    )
