"""Fixed race conditions for the v2 study (ADR-0024, docs/v2-plan.md).

A RaceConfig pins everything about a race that isn't the runner's own doing: start hour, a
looping weather cycle, and fixed-time schedules for special events and hallucinations. Every
runner in every run of the same config sees the same conditions at the same elapsed_min, so the
model driving the runner is the only variable left.

Data, not code — same as personas (agents/personas.py): configs live in server/races/*.yaml.

The one remaining source of sim randomness is GPS noise (course.believed_position). It draws from
gps_rng(seed, elapsed_min), a fresh generator per tick keyed on sim time, never a shared stream —
so noise at a given minute doesn't depend on how many draws earlier ticks happened to make, and
resume needs no saved rng state.
"""

import hashlib
import re
from pathlib import Path
from random import Random

import yaml
from pydantic import BaseModel, Field, field_validator

from models import EventType
from sim.sim_constants import WEATHER_CONDITIONS

RACES_DIR = Path(__file__).parent.parent / "races"

# race names arrive from POST /run's query string — this keeps them to a bare file stem, so a
# name can never point outside RACES_DIR
_RACE_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")


class WeatherPhase(BaseModel):
    condition: str
    duration_min: float = Field(gt=0)

    @field_validator("condition")
    @classmethod
    def _known_condition(cls, value: str) -> str:
        if value not in WEATHER_CONDITIONS:
            raise ValueError(f"unknown weather {value!r}, expected one of {WEATHER_CONDITIONS}")
        return value


class ScheduledEvent(BaseModel):
    # gt=0: an event fires on the tick whose window (prev, now] contains it, and the first tick's
    # window starts at 0 — so 0 itself could never fire
    at_elapsed_min: float = Field(gt=0)
    event: EventType

    @field_validator("event")
    @classmethod
    def _not_found_book(cls, value: str) -> str:
        if value == "found_book":
            raise ValueError("found_book comes from walking past a book, it can't be scheduled")
        return value


class ScheduledHallucination(BaseModel):
    at_elapsed_min: float = Field(gt=0)
    text: str


class RaceConfig(BaseModel):
    name: str
    seed: int
    start_hour: float = Field(ge=0, lt=24)
    weather_cycle: list[WeatherPhase] = Field(min_length=1)
    events: list[ScheduledEvent] = []
    hallucinations: list[ScheduledHallucination] = []


def load_race_config(name: str) -> RaceConfig:
    """Raises ValueError for a malformed name, FileNotFoundError for a missing file, and
    pydantic.ValidationError for a file that doesn't fit the schema."""
    if not _RACE_NAME_RE.fullmatch(name):
        raise ValueError(f"invalid race name {name!r}")
    with (RACES_DIR / f"{name}.yaml").open() as f:
        data = yaml.safe_load(f)
    return RaceConfig.model_validate(data)


def config_hash(config: RaceConfig) -> str:
    """Content hash stored in every checkpoint, so a resume can refuse a config that was edited
    after the race started (ADR-0024) rather than silently mixing two sets of conditions."""
    return hashlib.sha256(config.model_dump_json().encode()).hexdigest()


def weather_at(config: RaceConfig, elapsed_min: float) -> str:
    cycle_min = sum(phase.duration_min for phase in config.weather_cycle)
    into_cycle = elapsed_min % cycle_min
    for phase in config.weather_cycle:
        if into_cycle < phase.duration_min:
            return phase.condition
        into_cycle -= phase.duration_min
    return config.weather_cycle[-1].condition  # float rounding at the very end of a cycle


def events_due(config: RaceConfig, prev_elapsed_min: float, elapsed_min: float) -> list[str]:
    """Scheduled events falling in this tick's window (prev, now], in schedule order. Usually
    zero or one; more only if the schedule packs several into one tick."""
    due = [e for e in config.events if prev_elapsed_min < e.at_elapsed_min <= elapsed_min]
    return [e.event for e in sorted(due, key=lambda e: e.at_elapsed_min)]


def hallucination_due(
    config: RaceConfig, prev_elapsed_min: float, elapsed_min: float
) -> str | None:
    """The scheduled hallucination in this tick's window (prev, now], if any. If a schedule packs
    two into one tick, the later one wins — Observation.hallucination holds one line."""
    due = [h for h in config.hallucinations if prev_elapsed_min < h.at_elapsed_min <= elapsed_min]
    return max(due, key=lambda h: h.at_elapsed_min).text if due else None


def gps_rng(seed: int, elapsed_min: float) -> Random:
    """A str seed is hashed deterministically by Random (unlike the built-in hash(), which is
    randomized per process), so this is the same generator in every process and every run."""
    return Random(f"{seed}:gps:{elapsed_min:.6f}")
