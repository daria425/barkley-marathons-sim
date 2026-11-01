"""Representation of the state of the simulation world (Frozen Head State Park, Barkley location).

Terrain/elevation live in course.py instead — those are a function of where on the GPX
track the runner is, not of the weather. This file only knows about time and sky.

No randomness (ADR-0024): the weather condition is handed in by the caller from the race
config's fixed cycle, and everything else here is a pure function of it plus the clock.
"""

from dataclasses import dataclass

from sim.sim_constants import WEATHER_OFFSETS
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
    hour = calculate_hour(start_hour, elapsed_min)
    # 7am-7pm is daylight in Frozen Head State Park, around March - April
    return 7 <= hour < 19


def compute_temperature(elapsed_min: float, start_hour: float, weather: str) -> float:
    """Diurnal curve (cooler at night, peak afternoon) + weather offset."""
    hour = calculate_hour(start_hour, elapsed_min)
    # diurnal curve: peak at 15:00, low at 3:00
    diurnal_temp = -5 * (hour - 15) ** 2 / 36 + 20
    # if  there  is a key error thats our fuckery
    weather_offset = WEATHER_OFFSETS[weather]
    return diurnal_temp + weather_offset


def compute_fog_pct(weather: str, is_daylight: bool) -> float:
    """Weather-driven (fog/storm raise it), with a night bump. Feeds navigation noise — see
    CLAUDE.md's 'Comedy engine: true vs believed position'."""
    base = 0.0
    if weather == "fog":
        base += 50.0
    elif weather == "storm":
        base += 20.0
    if not is_daylight:
        base += 10.0
    return min(100.0, base)


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


def conditions_at(elapsed_min: float, start_hour: float, weather: str) -> FrozenHeadStatePark:
    """The park's conditions at a given sim-minute under a given weather. `weather` comes from
    the caller (sim/race_config.weather_at, ADR-0024) — this module has no randomness and no
    knowledge of the race config, only of what a weather condition does to the sky."""
    is_daylight = compute_is_daylight(elapsed_min, start_hour)
    temperature_c = compute_temperature(elapsed_min, start_hour, weather)
    return FrozenHeadStatePark(
        elapsed_min=elapsed_min,
        weather=weather,
        temperature_c=temperature_c,
        is_daylight=is_daylight,
        fog_pct=compute_fog_pct(weather, is_daylight),
        heat_index=compute_heat_index(temperature_c, weather),
        local_time=format_local_time(start_hour, elapsed_min),
    )


def tick(
    state: FrozenHeadStatePark, dt_min: float, start_hour: float, weather: str
) -> FrozenHeadStatePark:
    """Advance the park's conditions by one tick. This is the one function the sim loop calls."""
    return conditions_at(state.elapsed_min + dt_min, start_hour, weather)


def initial_state(start_hour: float, weather: str) -> FrozenHeadStatePark:
    """Race-start conditions. Both come from the race config (ADR-0024): start_hour because
    Barkley's horn blows any time midnight-noon, so never hardcode a sunrise assumption here."""
    return conditions_at(0.0, start_hour, weather)
