"""Shared RaceConfig builder for tests — a small, explicit config rather than races/study-01.yaml,
so editing the real study schedule never breaks a test that's about something else."""

from pathlib import Path

import yaml

from sim.race_config import RaceConfig, ScheduledEvent, ScheduledHallucination, WeatherPhase


def make_race_config(
    events: list[tuple[float, str]] = (),
    hallucinations: list[tuple[float, str]] = (),
    **overrides,
) -> RaceConfig:
    fields = {
        "name": "test-race",
        "seed": 1234,
        "start_hour": 6.0,
        "weather_cycle": [
            WeatherPhase(condition="clear", duration_min=120),
            WeatherPhase(condition="fog", duration_min=120),
            WeatherPhase(condition="rain", duration_min=120),
        ],
        "events": [ScheduledEvent(at_elapsed_min=t, event=e) for t, e in events],
        "hallucinations": [
            ScheduledHallucination(at_elapsed_min=t, text=text) for t, text in hallucinations
        ],
    }
    return RaceConfig(**{**fields, **overrides})


def write_race_config(races_dir: Path, config: RaceConfig) -> None:
    """Writes `config` as races_dir/<name>.yaml — for tests that go through load_race_config
    (e.g. POST /run) with sim.race_config.RACES_DIR monkeypatched to a tmp dir."""
    (races_dir / f"{config.name}.yaml").write_text(yaml.safe_dump(config.model_dump()))
