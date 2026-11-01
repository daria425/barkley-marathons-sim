# ADR-0024: Fixed race conditions via `RaceConfig`

**Date**: 2026-10-31
**Status**: accepted
**Deciders**: Daria

## Context

v2 turns the sim into a study: several models run the same persona under the same conditions so
the model is the only variable (`docs/v2-plan.md`). v1's conditions were deliberately random,
all drawn from one unseeded `random.Random()` (ADR-0003): start hour, Markov weather,
temperature/fog jitter, terrain-gated event rolls (ADR-0016), hallucination rolls (ADR-0017), GPS
noise. Seeding that rng isn't enough: event rolls only draw on certain terrain or at night, so
the number of draws per tick depends on the runner's path, and once two runs diverge even their
weather differs.

## Decision

Every race condition comes from a `RaceConfig` data file (`server/races/<name>.yaml`, loaded by
`sim/race_config.py`): `seed`, `start_hour`, a looping `weather_cycle`, and fixed-time `events`
and `hallucinations` schedules. There is no shared rng. GPS noise, the only sim randomness left,
draws from a fresh `Random(f"{seed}:gps:{elapsed_min}")` each tick. Temperature and fog are pure
functions of weather and clock. `POST /run` requires `race=<name>`. No backwards-compatible random
mode: reverting is `git checkout`.

Details:

- **Events** fire at their scheduled minute wherever the runner is (terrain gating dropped). One
  landing on a `found_book` tick waits in `pending_events` and goes out next tick, one per tick,
  so every runner receives every scheduled event.
- **Hallucination lines** fire from the schedule. Memory jumbling still uses `severity()`, with
  `HALLUCINATION_ONSET_MIN`/`RAMP_MIN` moved from dev values (1h/4h) to the real 40h/55h.
- **Checkpoint** drops `rng_state` and gains `race_config_name`, `race_config_hash` and
  `pending_events`. `restore_state` raises `RaceConfigMismatch` if the config's name or content
  hash differs; `main.py`'s supervisor doesn't retry it.
- **study-01**: 06:00 start, clear 2h → fog 2h → rain 2h looping, 38 events placed to fit weather
  and darkness (wildlife at night, puddles in rain, trips in fog/rain), 16 hallucinations from 40h.
- LLM sampling temperature is out of scope here; it belongs to the OpenRouter phase.

Amends ADR-0003 (explicit injection still holds for GPS noise, but the single shared generator is
gone), ADR-0016 (events scheduled, not rolled) and ADR-0017 (lines scheduled, jumble onset 40h).

## Alternatives Considered

### Alternative 1: Seed the existing shared rng

- **Pros**: a one-line change; keeps v1's random texture.
- **Cons**: draw counts depend on the runner's path, so conditions diverge between runs.
- **Why not**: fails the one property the study needs.

### Alternative 2: Separate seeded stream per source (weather, events, …)

- **Pros**: keeps random-looking conditions that are reproducible per seed.
- **Cons**: events would still be gated on terrain, so runners on different ground get different
  events; harder to read and reason about than a schedule.
- **Why not**: Daria chose fully fixed conditions; scheduled events give every model the same
  stimulus at the same moment.

### Alternative 3: Position-based events (fire at km X)

- **Pros**: events stay tied to places on the course.
- **Cons**: fast and slow models hit them at different times; models off trail never reach them.
- **Why not**: confounds the comparison.

### Alternative 4: Remove events and hallucinations entirely

- **Pros**: simplest, cleanest control.
- **Cons**: loses the mechanics that make runs interesting to compare.
- **Why not**: Daria wanted them kept, at fixed points.

## Consequences

### Positive

- Same config gives every runner identical weather, events and hallucinations regardless of its
  decisions (`test_conditions_are_identical_whatever_the_runner_decides`; a scripted 60h
  `study-01` run delivers 38/38 events and 16/16 hallucinations).
- Resume is simpler: no rng state to serialize; the config rebuilds everything.
- Each checkpoint records exactly which conditions produced it.

### Negative

- Events can read oddly out of context (a puddle on a dry ridge if the schedule ignores weather).
- Runs no longer differ in conditions; variety now comes only from the model and its sampling.
- Editing a config mid-race strands that race's checkpoint (by design).

### Risks

- A study run shorter than 40h never reaches hallucinations or memory jumbling; noted in
  CLAUDE.md's Live Testing section.
- Schedules are hand-written and easy to get wrong; `test_study_01_loads_and_its_schedule_fits_its_own_conditions`
  checks study-01's own rules.
