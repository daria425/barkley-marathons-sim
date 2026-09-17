# ADR-0003: Explicit `rng: random.Random` injection, never global `random.*` calls

**Date**: 2026-09-17
**Status**: accepted
**Deciders**: Daria

## Context

`frozen_head_state_park.py` needs real randomness (weather transitions, temperature jitter,
fog noise, initial weather pick). Calling `random.random()`/`random.choice()` directly inside
these functions would make them non-reproducible: Hypothesis couldn't shrink or replay a
failing case, and two test runs of the same inputs could disagree.

## Decision

Every function that needs randomness takes an explicit `rng: random.Random` parameter.
Production code passes a real `random.Random()` instance (owned by the caller — eventually
the sim loop or `RunnerState`); tests pass a seeded one. This keeps the functions
deterministic *given their inputs*, including the random ones, so they're still "pure" in
the sense that matters for testing even though the domain is inherently random.

## Alternatives Considered

### Alternative 1: Call `random.*` module-level functions directly

- **Pros**: Less boilerplate, no `rng` parameter threading through every signature.
- **Cons**: Untestable without monkeypatching the `random` module; can't seed a reproducible
  race replay later (useful for debugging "why did the runner do that").
- **Why not**: Directly conflicts with the property-testing bar CLAUDE.md sets for
  `physiology.py`, and we wanted the same testing rigor for weather.

## Consequences

### Positive

- Property tests can seed `random.Random(seed)` and get fully reproducible tick sequences —
  `test_frozen_head_state_park.py`'s `test_tick_sequence_stays_valid` relies on this.
- Leaves the door open for deterministic race replay/debugging later (same seed = same race).

### Negative

- Every new randomness-needing function in `sim/*.py` must remember to take `rng` as a
  parameter instead of reaching for `random.random()` — easy to forget without review.

### Risks

- Risk: someone adds a bare `random.*` call in `course.py` or elsewhere without following
  this convention. Mitigation: this ADR + code review; could add a ruff/grep check later if
  it becomes a recurring slip.
