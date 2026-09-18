"""Pydantic wire format: what's broadcast over the WebSocket and logged to SQLite.

Internal simulation math (physiology, weather) lives in sim/*.py as plain frozen
dataclasses; these models embed those dataclasses as fields rather than duplicating
their shape. Pydantic v2 validates/serializes stdlib dataclasses natively.
"""

from pydantic import BaseModel

from sim.frozen_head_state_park import FrozenHeadStatePark
from sim.physiology import PhysiologyState


class Observation(BaseModel):
    elapsed_min: int
    clock_time: str  # e.g. "Day 2, 3:15 AM" — sim_utils.format_clock_time(start_hour, elapsed_min)
    hr: int
    pace_min_per_km: float
    cadence: int
    feel: str  # "legs heavy", "bonking", etc.
    last_ate_min_ago: int
    bearing_deg: float
    gps_guess: tuple[float, float]  # NOISY believed position
    terrain: str  # "thick briars", "creek crossing"
    weather: str
    books_found: int
    loop: int
    hallucination: str | None


class Decision(BaseModel):
    effort: int  # 1-10
    eat: bool
    drink: bool
    bearing_deg: float
    rest_min: int
    quit: bool
    monologue: str


class RunnerState(BaseModel):
    """Everything about one runner, broadcast/logged as-is. Wraps PhysiologyState
    rather than re-declaring its fields."""

    persona_name: str
    physiology: PhysiologyState
    true_pos: tuple[float, float]
    believed_pos: tuple[float, float]  # NOISY — see CLAUDE.md's "true vs believed position"
    loop: int
    books_found: int
    pace_min_per_km: float
    feel: str
    last_decision: Decision | None = None


class RaceState(BaseModel):
    """The full broadcast snapshot: sim clock, environment, every runner.
    Named RaceState (not WorldState) to avoid colliding with FrozenHeadStatePark,
    which owns the weather/environment data this model embeds."""

    elapsed_min: float
    environment: FrozenHeadStatePark
    runners: dict[str, RunnerState]  # keyed by persona_name, for v1's single runner too
