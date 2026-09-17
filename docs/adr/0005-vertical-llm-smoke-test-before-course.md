# ADR-0005: Vertical LLM smoke-test slice before building `course.py`

**Date**: 2026-09-17
**Status**: proposed
**Deciders**: Daria

## Context

CLAUDE.md's build order is weather → physiology → course/books/navigation → LLM persona.
Weather and physiology are done. But the highest-risk, least-proven part of this project is
the brain loop itself — prompt shape, structured-decision parsing, persona voice, and
watching monologues stream live — not the navigation math. Building `course.py` first would
mean writing a real GPX/books/terrain system before ever confirming the LLM integration works
at all.

## Decision

Insert a throwaway vertical slice: wire up `agents/brain.py` + one persona + a minimal
`sim/loop.py`, run it for a few real minutes against **stubbed** course-dependent Observation
fields (fixed coords, hardcoded terrain, `loop=1`, `books_found=0`), and confirm one full
Observation → Decision → monologue round-trip logs correctly. `course.py` gets built for real
immediately after, replacing the stubs. Brain-call cadence for this slice is every tick, with
`dt_min=0.25` sim-minutes per tick (real-time ratio preserved — 15 real seconds per tick at
1x) rather than CLAUDE.md's undecided-but-implied 1-sim-minute tick, so the slice is fast
enough to iterate on live.

## Alternatives Considered

### Alternative 1: Build `course.py` first as CLAUDE.md originally ordered it

- **Pros**: no stubbing, no re-ordering to explain later.
- **Cons**: sinks time into navigation/terrain design before knowing if the brain loop's
  prompt/parsing/persona shape even works.
- **Why not**: navigation is the lower-risk, more mechanical piece; the LLM loop is what
  could actually go wrong in a surprising way.

### Alternative 2: Keep dt_min=1 sim-minute per tick for the slice too

- **Pros**: matches CLAUDE.md's "1 tick = 1 sim-minute" literally, no new constant to track.
- **Cons**: at real-time (1x), each brain call takes a full 60 real seconds to observe — slow
  for iterating on prompt/parsing bugs.
- **Why not**: finer tick granularity doesn't change any physiology semantics (dt_min already
  flows through as a parameter), it's a legitimate tuning knob, not a hack.

## Consequences

### Positive

- Proves the riskiest integration (Anthropic call → parsed `Decision` → persona voice) before
  investing in navigation.
- `dt_min=0.25` is fast enough to watch multiple decisions per minute of wall-clock time
  during dev.

### Negative

- Stubbed Observation fields (terrain/gps/bearing/books) get thrown away once `course.py`
  lands — genuinely temporary code.
- Real per-tick cadence (the "N" CLAUDE.md leaves undecided) still isn't chosen for the actual
  race — this ADR only fixes it for the smoke test.

### Risks

- Risk: the 0.25-min tick becomes accidentally permanent instead of being revisited once real
  navigation exists. Mitigation: this ADR + a TODO comment at the constant's definition.
