# ADR-0016: Generalized special-event system, extending `Observation.event` past `found_book`

**Date**: 2026-09-25
**Status**: accepted
**Deciders**: Daria

## Context

ADR-0015 introduced `Observation.event: Literal["found_book"] | None` and explicitly designed it
to extend: "Other trigger events (fall, lost, bonk, loop complete, quit consideration) can extend
the same `Literal` and the same `if obs.event == ...` branch in `format_observation` later." That
"later" is now — the next milestone calls for comedic trigger events beyond books (tripping,
puddles, wildlife, etc.), which is squarely what ADR-0015 left open.

## Decision

Extend `EventType` (a shared Literal, `models.py`) with five new values: `tripped_and_fell`,
`stepped_in_puddle`, `briar_scratch`, `spooked_by_wildlife`, `dropped_water_bottle`. A new pure
`sim/course.py:detect_special_event(terrain, grade_pct, is_daylight, rng)` rolls each in a fixed
priority order (each an early return, so at most one fires), gated by terrain/grade/time-of-day,
using the project's existing injected-`Random` convention (matching `believed_position`).
`sim/loop.py`'s `advance_tick()` only rolls a special event when no book was found that tick —
book-found always wins, preserving ADR-0015's single-event-per-tick shape rather than widening
`event` to a list. `agents/memory.py` extends `format_observation` (a prompt line per event) and
its compaction: `SegmentFacts` gained `event_counts` (non-book events, tallied so they survive
aging out of the sliding window) and `_pick_highlight_turn` now ranks a special event above the
"nothing happened" fallback but below quit/collapse/bonk/book-found. `RunnerState` gained
`last_event` so events reach the WS wire format (frontend `raceSlice.ts` tracks an `events` map
alongside the existing `monologues` map) — deliberately with no UI rendering yet.

## Alternatives Considered

### Alternative 1: Allow multiple concurrent events per tick (`event: list[str]`)

- **Pros**: more realistic — nothing stops a trip and a puddle genuinely coinciding.
- **Cons**: touches every consumer (`format_observation`, compaction, wire model, DB) for a purely
  comedic gain; ADR-0015's "geometrically can't double-fire" proof was book-specific and doesn't
  extend to terrain-gated rolls, so a collision is now merely *possible*, not *inevitable*.
- **Why not**: kept single-event-per-tick, with book-found given priority by construction (checked
  first, special-event roll skipped when a book fires) — simplest fix for the rare-collision case,
  no schema widening needed for what's still flavor text.

### Alternative 2: Fold ADR-0001's deferred hallucinations into this same pass

- **Pros**: ADR-0001 said hallucinations should wait until Observation/memory/navigation exist to
  receive them — now true.
- **Cons**: hallucinations need sleep-debt/fatigue state that doesn't exist in `physiology.py` yet
  (no rng there at all) — a bigger, physiology-touching feature, not a terrain-flavor one.
- **Why not**: out of scope for this pass; ADR-0001 stays open and separate.

### Alternative 3: Make events queryable in SQLite now (own column/table)

- **Pros**: enables future stats ("how many times did runner X fall").
- **Cons**: no current consumer needs this; `turns` is already documented as a deliberately
  throwaway log shape.
- **Why not**: deferred — `event` stays embedded in `observation_json` until something actually
  needs to query it.

## Consequences

### Positive

- New event types are additive: a new `Literal` value + a `detect_special_event` branch + a
  `format_observation`/`_EVENT_PROMPT_LINES` entry, no scheduling or architecture changes
  (validates ADR-0015's design bet).
- Events survive memory compaction instead of silently vanishing once their turn ages out of the
  sliding window.
- Frontend wire format already carries `last_event`, so the later UI-rendering phase has no
  backend work left to do.

### Negative

- Per-tick probabilities are a tuning knob with no reference data yet (unlike physiology) — initial
  values were roughly 2x'd after a live 75-min/300-tick dev-slice test showed too few events to
  observe; still an eyeballed guess, not validated against real ultrarunning incident rates.
- `detect_special_event`'s priority order (trip > puddle > briar > wildlife > bottle-drop) is
  arbitrary and untested against what actually reads best in practice.

### Risks

- Terrain-gated rolls are not geometrically bounded the way book-spacing was in ADR-0015 — a trip
  and a puddle *could* both want to fire on the same tick on qualifying terrain; resolved by
  priority order (book only checked as a separate, higher-priority gate), not by proving it can't
  happen.
- Fixed twenty pre-existing test failures while landing this: stale fixtures (`test_memory.py`,
  `test_participant.py`, `test_db.py`) missing the required `Observation.event` field from
  ADR-0015, and one `test_course.py` test not unpacking `books_found_this_tick`'s
  `(frozenset, bool)` tuple return. Unrelated to this ADR's decision but discovered and fixed
  alongside it.
