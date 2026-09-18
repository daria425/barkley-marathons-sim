# ADR-0010: Free 2D navigation in `sim/course.py`, and books as a proximity counter

**Date**: 2026-09-18
**Status**: accepted
**Deciders**: Daria

## Context

`sim/course.py` was the last stubbed piece of v1 (ADR-0005) — Observation's position, terrain,
bearing, and books fields were hardcoded constants in `sim/loop.py`. Building it for real raised
two design questions: how should true position actually move given a runner's chosen bearing,
and how much of Barkley's real book/bib rule needs modeling. Planning initially proposed
representing position as 1-D progress along the course polyline, with a bearing-mismatch penalty
standing in for "wandering off course." On review, free 2D movement turned out to need *less*
code than that penalty scheme, not more, so the plan changed before any of it was written.

## Decision

`true_pos` is a genuine free `(lat, lon)`, advanced each tick by a haversine destination-point
formula: `advance_position(pos, bearing_deg, distance_km)`, where `distance_km` comes from
`physiology.compute_pace()` (now fed a real `grade_pct` computed from the GPX-derived polyline,
a parameter that function already accepted but nothing supplied before). A bad
`decision.bearing_deg` simply walks the runner in the wrong direction — no comparison against a
"true course bearing," no progress penalty.

The GPX track (16k raw points) is resampled once to ~600 points at 50m spacing and cached
(`lru_cache`), used only for: placing 13 books at fixed, evenly-spaced distances around the loop
(not rng-placed); deriving `terrain_at`/`grade_pct_at` via brute-force nearest-point scan (cheap
at ~600 points); and detecting loop completion (distance covered since the last completion
exceeds half the loop, and position is back near the start/finish).

Real Barkley requires collecting the book page matching your bib number, from every book, every
loop. Since v1 has one runner and the sim doesn't model page contents, this needs no real
mechanic: `books_found` is a plain per-loop proximity counter (`books_found_this_tick`), and the
collected set resets on loop completion — matching "a fresh page each loop" without simulating
pages. The one change this motivated: a `bib_number` field added now to `Persona`
(`agents/personas.py`) and `RunnerState` (`models.py`), cheaply, ahead of when multi-persona
will actually need distinct bibs — same reasoning CLAUDE.md already applies to building the
concurrency semaphore before it's needed.

Added the `haversine` PyPI package (already named in CLAUDE.md's Stack section for this purpose,
just not yet installed) for `haversine()` distance and `inverse_haversine()` destination-point
calls. Confirmed empirically that its `Direction` is radians clockwise from north — the same
convention as `bearing_deg` — so no remapping is needed beyond `math.radians()`.

## Alternatives Considered

### Alternative 1: 1-D progress along the course + bearing-mismatch penalty

- **Pros**: guarantees the runner stays "on the map" the frontend will eventually draw; no
  chance of wandering arbitrarily far from the course.
- **Cons**: needs a "true course bearing at this point" concept and a penalty formula scaling
  distance by bearing error — more moving parts than just letting the runner walk where they
  point.
- **Why not**: free 2D produces the same comedy (bad bearing → lost, not found books, wasted
  time) from plain geometry, with less code and no special-casing.

### Alternative 2: Model per-book page/bib matching mechanics now

- **Pros**: matches the real Barkley rule exactly; would already be in place for multi-persona.
- **Cons**: pure bookkeeping with no payoff until there's more than one runner — v1 has nothing
  to distinguish bib-holders from each other.
- **Why not**: premature for a single-runner v1. `bib_number` is added now as the cheap hook;
  the actual per-runner-page logic is deferred to the multi-persona phase.

## Consequences

### Positive

- Movement code is simpler than the originally planned progress-penalty model — no coupling
  between the runner's chosen heading and the trail geometry.
- `grade_pct` flowing into `physiology.compute_pace()` wires up a parameter that already existed
  but was previously always `0.0`.
- `bib_number` existing on `Persona`/`RunnerState` now means multi-persona doesn't need a schema
  change later, just distinct values.

### Negative

- Off-trail terrain/grade is necessarily generic (`"thick brush, no trail in sight"`, grade
  `0.0`) — there's no elevation data beyond the mapped GPX track, so full bushwhacking physics
  (thicker brush = slower, off-trail elevation) stays out of scope.
- Free-roam movement means a runner can in principle wander arbitrarily far from the course with
  no boundary — no "search and rescue" or bounds-checking mechanic exists yet.

### Risks

- Risk: an unlucky sequence of bad bearings walks a runner far enough from the polyline that
  `terrain_at`/`grade_pct_at` stay generic for a long stretch, and they may never re-find the
  loop to complete it. Mitigation: none yet — acceptable for v1's "watch it run and see what
  happens" scope (CLAUDE.md, no race-end concept yet); revisit if it makes runs uninteresting to
  watch.
