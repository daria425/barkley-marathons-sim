# ADR-0015: Per-tick brain-call cadence, with book-found surfaced via `Observation.event`

**Date**: 2026-09-24
**Status**: accepted
**Deciders**: Daria

## Context

CLAUDE.md originally left brain-call cadence open: "either every N sim-minutes or on trigger
events... N is not decided yet." Building event-gated calls means detection logic for each
trigger (fall, lost, bonk, book found, loop complete, quit consideration) plus a scheduler
deciding which ticks warrant a call — none of which existed yet.

A narrower version of the same question came up first while wiring `books_found_this_tick`:
`Observation.books_found` was a bare running count, so the LLM could only learn it found a new
book by diffing counts against its own sliding-window history — fragile once
`agents/memory.py`'s compaction folds the turn where the count changed (ADR-0008/0012).

Also raised and checked during this decision: whether the current tick size (`TICK_DT_MIN =
0.25` sim-min, 15 real seconds) lets a runner cover unrealistic ground between checks. It
doesn't — see Consequences.

## Decision

Keep brain calls firing on **every tick**, unconditionally (`sim/loop.py`'s `run()` loop already
did this; this ADR makes it the settled answer to CLAUDE.md's "N is not decided yet" rather than
a placeholder). No event-gating scheduler is built.

Trigger-worthy moments get surfaced through the Observation itself instead of through call
scheduling: `course.books_found_this_tick` now returns `tuple[frozenset[int], bool]`, the bool
threaded through `advance_tick` into a new `Observation.event: Literal["found_book"] | None`
field (`models.py`). `agents/memory.py`'s `format_observation` appends an explicit line when set:
`"You just found a book at {gps_guess}!"`. Since every tick already produces a fresh Observation
for the brain, "something notable just happened" is just a richer Observation, not a new
mechanism. Other trigger events (fall, lost, bonk, loop complete, quit consideration) can extend
the same `Literal` and the same `if obs.event == ...` branch in `format_observation` later.

## Alternatives Considered

### Alternative 1: Event-gated brain calls (only call the brain on trigger events)

- **Pros**: far fewer LLM calls.
- **Cons**: needs a dispatcher deciding which ticks matter, detection logic per trigger type, and
  still doesn't solve "how does the LLM learn a book was found" on its own — that field/line was
  needed either way.
- **Why not**: for v1's single runner, the simpler per-tick cadence matches ADR-0007's
  vertical-slice-first bias — build the thin thing, add gating later if cost or noise actually
  becomes a problem. The `$` cost is known and acceptable (see Consequences).

### Alternative 2: Leave `books_found` as a plain count, let the LLM infer new finds

- **Pros**: no schema change, no `format_observation` change.
- **Why not**: relies on the LLM correctly diffing counts across turns and survives compaction —
  unreliable for a mechanic (finding a book) that's meant to matter enough to react to
  in-character.

## Consequences

### Positive

- No scheduler/dispatcher needed; "notable moment" is just a field on the Observation that's
  already sent every tick.
- `event` is a `Literal` that can grow (fall, lost, bonk, etc.) without touching call cadence.

### Negative

- A full 60h race is `60 * 60 / 0.25 = 14,400` ticks, i.e. brain calls, per runner — the large
  majority of which are "nothing happened." At Haiku pricing this was previously estimated at
  roughly $60 for one full-length sim, which is fine for the handful of full runs planned for v1
  but would need revisiting before running many full sims or scaling to multi-persona (5-10
  runners × 14,400 calls each).

### Risks

- **"Can the runner outrun the book-proximity check and skip over one, or find two in a single
  tick?"** — checked, not a real risk: books are evenly spaced along the ~32.4km loop
  (`total_km / (N_BOOKS + 1) ≈ 2.3km` apart), while `BOOK_PROXIMITY_KM = 0.05km`. The fastest
  possible pace (`compute_pace`'s floor, `base_pace * 0.5` = 5 min/km) covers at most
  `0.25 / 5 = 0.05km` per tick — exactly the proximity radius, two orders of magnitude below the
  book spacing. A runner cannot cover 2.3km in 15 sim-seconds; `event` only ever needing to carry
  one flag per tick is a consequence of that, not a limitation being papered over.
- `event` collapsing "which book" into a single flag means the exact book index isn't surfaced to
  the LLM directly (only via the `books_found` count going up) — acceptable since the monologue
  doesn't need to distinguish book identity, only that one was found.
