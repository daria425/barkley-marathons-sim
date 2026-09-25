"""Pydantic wire format: what's broadcast over the WebSocket and logged to SQLite.

Internal simulation math (physiology, weather) lives in sim/*.py as plain frozen
dataclasses; these models embed those dataclasses as fields rather than duplicating
their shape. Pydantic v2 validates/serializes stdlib dataclasses natively.
"""

from typing import Literal

from pydantic import BaseModel

from sim.frozen_head_state_park import FrozenHeadStatePark
from sim.physiology import PhysiologyState

# Single event per tick (see ADR-0015/ADR-00XX) — detectors run in a fixed priority order and
# the first hit wins. Add new values here as other trigger events land.
EventType = Literal[
    "found_book",
    "tripped_and_fell",
    "stepped_in_puddle",
    "briar_scratch",
    "spooked_by_wildlife",
    "dropped_water_bottle",
]


class Observation(BaseModel):
    elapsed_min: int
    # e.g. "Day 2, 3:15 AM" — sim_utils.format_clock_time(start_hour, elapsed_min)
    clock_time: str
    hr: int
    pace_min_per_km: float
    cadence: int
    feel: str  # "legs heavy", "bonking", etc.
    last_ate_min_ago: int
    bearing_deg: float
    gps_guess: tuple[float, float]  # NOISY believed position
    dist_to_trail_km: float  # raw distance to nearest trail point — continuous, not clamped
    # to the on/off-trail threshold, so it reads as a trend across turns rather than a flip
    terrain: str  # "thick briars", "creek crossing"
    event: EventType | None
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
    bib_number: int  # real Barkley bibs are odd numbers — see ADR-0010
    physiology: PhysiologyState
    true_pos: tuple[float, float]
    current_terrain: str  # same values as Observation.terrain, frontend-facing name
    # NOISY — see CLAUDE.md's "true vs believed position"
    believed_pos: tuple[float, float]
    loop: int
    books_found: int
    pace_min_per_km: float
    feel: str
    last_decision: Decision | None = None
    # most recent Observation.event, mirrored onto the wire for frontend consumption — not
    # rendered yet, just made available (no UI hookup in this phase)
    last_event: EventType | None = None


class Checkpoint(BaseModel):
    """Full resumable state for one runner — see ADR-0008. Rewritten wholesale (INSERT OR
    REPLACE, keyed by runner_id) on every brain decision, unlike the append-only `turns` log.

    `rng_state` must round-trip exactly through db.py's rng (de)serialization helpers, not bare
    json.dumps/loads — see their docstrings for why. Bit-exact RNG resume is a deliberate
    choice (not just convenience): a checkpoint that let weather/noise diverge after a crash
    would make "resume" produce a provably different race, not a continuation of the same one.
    """

    runner_id: str
    elapsed_min: float
    physiology: PhysiologyState
    environment: FrozenHeadStatePark
    start_hour: float
    true_pos: tuple[float, float]
    believed_pos: tuple[float, float]
    loop: int
    books_found: int
    # ADR-0010: resets each loop, real Barkley rule
    books_collected_this_loop: list[int] = []
    dist_since_loop_start_km: float = 0.0  # ADR-0010's loop-completion heuristic
    last_ate_min_ago: float
    last_decision: Decision
    rng_state: str
    summary_text: str
    summary_covers_up_to_elapsed_min: int
    summary_folded_count: int = 0


class RaceState(BaseModel):
    """The full broadcast snapshot: sim clock, environment, every runner.
    Named RaceState (not WorldState) to avoid colliding with FrozenHeadStatePark,
    which owns the weather/environment data this model embeds."""

    elapsed_min: float
    environment: FrozenHeadStatePark
    # keyed by persona_name, for v1's single runner too
    runners: dict[str, RunnerState]


class CourseBook(BaseModel):
    index: int
    name: str
    lat: float
    lon: float


class CourseGeometry(BaseModel):
    """The static course shape (trail polyline + book locations) for the frontend map. Never
    broadcast over /ws — fetched once via GET /course, since sim.course.load_course() is
    lru_cached and doesn't change mid-race."""

    # (lat, lon), oldest-to-loop-completion order
    points: list[tuple[float, float]]
    books: list[CourseBook]
