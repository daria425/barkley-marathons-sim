# ADR-0019: Race-end mechanism — finished / dnf_cutoff / dnf_quit

**Date**: 2026-09-29
**Status**: accepted
**Deciders**: Daria

## Context

CLAUDE.md explicitly deferred this: "No race-end concept yet... Finish-line/cutoff handling
gets designed later, once there's something worth finishing." That point has arrived. Today,
`state.loop` (`sim/loop.py`) increments forever with no cap, `Decision.quit` is read into
`agents/memory.py`'s compaction (highlight-turn priority, `quit_considered`) but has zero effect
on the sim, and `run()`'s tick loop just silently falls out of its `for _ in range(n_ticks)`
loop once `duration_min` is exhausted — nothing distinguishes "the race genuinely ended" from
"we just stopped watching," and no WS message announces either. The frontend (designed
separately, out of scope here) needs to differentiate a finish from a DNF off the WS stream.

## Decision

Add `RunnerStatus = Literal["running", "finished", "dnf_cutoff", "dnf_quit"]`
(`models.py`), carried on both `RunnerState` (wire format) and `Checkpoint` (persistence).
Three terminal conditions, checked once per tick by a new pure function
`_check_race_end(state, decision)` in `sim/loop.py`: **finished** once
`state.loop > TOTAL_LOOPS` (new constant, `sim/sim_constants.py`, = 5); **dnf_quit** if
`decision.quit` is true (this is the first place `Decision.quit` actually stops anything);
**dnf_cutoff** if the tick loop exhausts all of `duration_min` without either firing first —
`duration_min` (already flowing from `/run` into `n_ticks`) is now the literal race cutoff, not
just a dev-convenience early stop, so a short dev slice honestly reports `dnf_cutoff` too.
Whichever fires, the tick loop stops and broadcasts the terminal state exactly once
(`_finalize_race_end`); a resumed process that loads an already-terminal checkpoint
re-announces the outcome once and never re-enters the tick loop (`_resume_or_start` /
`_broadcast_already_ended_race`).

## Alternatives Considered

### Alternative 1: A separate `race_cutoff_min` (defaulting to 60h) independent of `duration_min`

- **Pros**: Keeps "how long to run before returning" (a dev/test convenience) cleanly separate
  from "the actual 60h Barkley cutoff" (a race rule) — a short dev slice would just stop
  quietly, the way it does today, without claiming the runner DNF'd anything.
- **Cons**: A second knob to keep in sync; `duration_min` already flows end-to-end from `/run`
  through to the tick count, so this duplicates a concept that already exists.
- **Why not**: Explicitly rejected — "for a slice run i think logic should be dnf cutoff right?
  ... too bad." A dev slice that stops the clock early genuinely didn't finish within the time
  it was given; that's not a lie, and it's simpler to have one meaning for `duration_min` than
  two.

### Alternative 2: `status` on `RaceState` (race-level) instead of `RunnerState` (per-runner)

- **Pros**: One field instead of one per runner; matches v1's single-runner mental model most
  directly.
- **Cons**: Doesn't extend to multi-persona (Build order step 4) without a rework — a race with
  several runners needs each one's finish/DNF tracked independently (one runner finishing
  doesn't end the race for the others).
- **Why not**: Per-runner costs nothing extra at v1 scale (still a one-entry `runners` dict) and
  is the only version of this field that's still correct once multi-persona lands.

### Alternative 3: Keep the silent stop, surface race-end only via `/status` polling

- **Pros**: No WS/model schema change at all.
- **Cons**: Contradicts CLAUDE.md's "no separate polling/REST-status endpoint needed" API
  surface decision, and defeats the point of a live WS stream — the frontend would have to poll
  to notice the one moment that matters most (the race ending).
- **Why not**: The whole ask was a WS notification; polling isn't that.

## Consequences

### Positive

- The frontend can render three distinct end states (finish banner, cutoff DNF, quit/Taps) off
  a single `RunnerState.status` field already riding the existing per-tick WS broadcast — no new
  endpoint, no change to `main.py`'s `_broadcast`/`/ws` wiring at all.
- `Decision.quit` finally does something — previously a purely cosmetic field.
- Resume is now race-end-aware: `POST /run` called again after a race already ended re-announces
  the outcome instead of silently ticking a finished/DNF'd runner for another `duration_min`.
- `main.py`'s crash-restart supervisor (`_supervised_run`) needed zero changes — it already
  treats any normal `run()` return (not just a full `duration_min` completion) as done.

### Negative

- `duration_min` now carries two meanings at once (dev-convenience bound and literal race
  cutoff) rather than being purely a test/iteration knob — a deliberate simplification (see
  Alternative 1), but it means every dev/live-test run (CLAUDE.md's Live Testing walkthrough)
  now ends with a `dnf_cutoff` checkpoint, not a clean "just stopped" state.
- `sim/loop.py`'s `run()` picked up enough new branching (three end conditions, resume
  short-circuit) that it tripped ruff's mccabe complexity budget; three small helpers
  (`_check_race_end`, `_finalize_race_end`, `_resume_or_start`, `_broadcast_already_ended_race`,
  `_maybe_fallback_checkpoint`) were pulled out to bring it back under 10. Net positive for
  readability, but it's more surface area than the original inline version.

### Risks

- Risk: `_check_race_end`'s "finished beats quit on the same tick" priority is untested against
  a real 5-loop course run (course completion wasn't exercised end-to-end here, only via a
  direct `state.loop` override in `tests/test_race_end.py` — full-course integration is
  expensive to simulate in a unit test). Mitigation: revisit once a real multi-loop run
  (sped-up slice or the eventual full 60h race) actually reaches loop 5.
