# ADR-0004: Sustained max-effort pushing through a bonk forces a physiological collapse

**Date**: 2026-09-17
**Status**: accepted
**Deciders**: Daria

## Context

`compute_pace()` floors pace at `start_pace_min_per_km * 0.5` so effort can never produce an
implausibly fast pace. Property testing surfaced that at RPE 10, this floor also swallowed the
bonk penalty entirely — a bonking runner at max effort showed the same pace as a fresh one,
since both clamped to the same floor. The first instinct was to treat this as a bug to
suppress; instead we reframed it as a feature: the Barkley Marathons is brutal enough that a
runner genuinely can redline through a bonk for a while, but not forever.

## Decision

Added `PhysiologyState.bonk_push_min` tracking sim-minutes spent bonking at
RPE >= `BONK_PUSH_EFFORT_THRESHOLD`, resetting the instant either condition breaks.
`has_collapsed(bonk_push_min)` flips true past `BONK_PUSH_LIMIT_MIN` (30 sim-min,
placeholder/tunable). `compute_pace(..., collapsed=True)` bypasses the floor entirely
(4x pace penalty), so gritting through a bonk stays fast-ish until the streak runs out, then
the body forces a real collapse regardless of what effort the Decision asks for.

## Alternatives Considered

### Alternative 1: Apply the bonk multiplier after the floor clamp

- **Pros**: Minimal change, no new state field.
- **Cons**: Loses the "you can push through it briefly" mechanic — bonking would just always
  be strictly worse than the floor, no matter how briefly it's happening. Less interesting
  narratively (no "runner is gritting through it" vs "runner physically can't continue" split).
- **Why not**: Flattens a genuinely comedic/realistic Barkley mechanic into a pure numeric fix.

## Consequences

### Positive

- Gives the sim a natural moment where physiology overrides the LLM's Decision — the body
  doesn't listen to the brain forever, which fits the "bad navigation, bonking, quitting"
  comedy the whole project is built around.
- `has_collapsed` is a clean hook for a future brain-call trigger event (alongside fall,
  lost, bonk, book found, loop complete, quit consideration in CLAUDE.md's core-loop list).

### Negative

- `compute_pace` no longer reads `bonk_push_min` itself — callers must compute
  `has_collapsed(state.bonk_push_min)` and pass the bool in. Slightly more wiring at the call
  site (the sim loop, not yet built) versus a self-contained function.

### Risks

- `BONK_PUSH_EFFORT_THRESHOLD` (7) and `BONK_PUSH_LIMIT_MIN` (30 sim-min) are untuned
  placeholders — revisit during the reference-data validation pass CLAUDE.md calls for.
