# ADR-0002: Pure sim state (physiology, weather) composed into Pydantic wire models

**Date**: 2026-09-17
**Status**: accepted
**Deciders**: Daria

## Context

`sim/physiology.py` and `sim/frozen_head_state_park.py` were built as frozen dataclasses with
pure step functions (`tick(state, ...) -> new_state`), so Hypothesis property tests can throw
random inputs at them without touching async/IO/API concerns. But CLAUDE.md's `models.py`
also calls for Pydantic `RunnerState`/`WorldState` — the shapes actually broadcast over the
WebSocket and logged to SQLite. The question was whether these are two different attempts at
the same thing, or genuinely separate layers.

## Decision

`models.py`'s Pydantic models **embed** the `sim/*.py` dataclasses as fields rather than
duplicating their shape: `RunnerState.physiology: PhysiologyState`, and the race-level model
embeds `FrozenHeadStatePark` under an `environment` field. Pydantic v2 validates/serializes
stdlib dataclasses natively, so no adapter layer is needed. `RunnerState`/the race model add
only what physiology/weather don't know about: persona identity, position (`true_pos`/
`believed_pos`), loop number, books found, and the Decision currently being executed.

## Alternatives Considered

### Alternative 1: Make physiology/weather Pydantic models directly

- **Pros**: One model system instead of two; `models.py` wouldn't need to know about `sim/*.py`.
- **Cons**: Pydantic model validation overhead on every tick (physiology/weather tick every
  sim-minute, broadcast happens less often); couples the pure-math modules to a
  serialization framework CLAUDE.md scoped to the API/DB layer.
- **Why not**: `physiology.py`'s hard requirement (CLAUDE.md) is to stay pure with no
  framework dependencies — ticking on every sim-minute is hot-path code, Pydantic isn't
  needed there.

## Consequences

### Positive

- Property tests for `sim/*.py` stay fast and framework-free.
- `models.py` fields stay honest about what's new at the wire-format layer vs. what's just
  passed through from the sim internals.

### Negative

- Two field-naming conventions to keep in sync by hand (e.g. if `PhysiologyState` gains a
  field, `RunnerState`'s embedding doesn't need a change, but anything *reading* physiology
  fields through `RunnerState.physiology.x` needs both files open).

### Risks

- None significant — this is a straightforward composition pattern, not a new abstraction.
