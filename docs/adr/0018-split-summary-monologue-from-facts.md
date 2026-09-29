# ADR-0018: Split the running summary into a monologue-free body plus a single replaced highlight

**Date**: 2026-09-29
**Status**: accepted
**Deciders**: Daria

## Context

A prod rerun (`speed=1`, `duration_min=75`, session `Hank`, 300 brain calls) showed input tokens
per call growing from ~1,480 at tick 1 to ~10,200 by tick 300, with a measured post-window-fill
slope of ~7.9 input tokens/tick. Extrapolated linearly across the full 14,400-tick/60h race, that
projects to **~122,000 input tokens per call by the end** — still under Haiku 4.5's 200K context
window, but climbing the whole race with no ceiling in sight.

ADR-0012 fixed the growth *rate* (batching instead of one redundant re-summarization per tick)
but not the *ceiling*: `agents/memory.py`'s `compact_if_needed` still does
`new_summary = f"{summary}\n{segment_text}"` on every fold, forever. ADR-0012's own Risks section
flagged this as worth revisiting once a real run's numbers were in — this is that revisit.

Inspecting the actual summary text from the rerun (13 folded segments, 7,545 chars) showed every
segment carries a full quoted `highlight_monologue` (300-500 chars) against ~100-150 chars of
facts-only text (books/feel/food/rest). Monologues are roughly 70-80% of segment bytes — Hank's
persona narrates his own pace/HR/distance numbers back to himself in nearly every fold, none of
which he'd plausibly still be reciting minutes later.

## Decision

Split the running summary into two pieces instead of one flat string. `summary_body` is the
ever-growing, monologue-free facts log (unchanged growth shape from ADR-0012 — one line per
folded batch). `latest_highlight` is just the most recently folded segment's quoted monologue,
**replaced, not appended,** on every fold — exactly one monologue quote exists in the prompt at
any time, never a chain of every thought Hank has ever had. The two are joined only at
prompt-render time (`agents/participant.py`), never stored pre-joined, so `Checkpoint` persists
them separately (`summary_body: str`, `latest_highlight: str = ""`, replacing the old
`summary_text: str`).

## Alternatives Considered

### Alternative 1: Hard cap + re-fold oldest segments once summary_body exceeds a size threshold

- **Pros**: Caps summary size regardless of race length, batch size, or how this sample's
  monologue/facts ratio holds up in practice — the actual ceiling, not just a much lower slope.
- **Cons**: A second compaction pass (its own threshold, its own re-fold logic) on top of the one
  ADR-0008/0012 already added; a real second untestable-in-production dimension to tune.
- **Why not**: Once monologues are stripped, `summary_body`'s growth is bounded by the race's own
  fixed length (60h/14,400 ticks) rather than truly unbounded — projected end-of-race size drops
  to ~30-37K tokens, comfortably under the 200K context window. A cap would flatten the
  cost/latency curve further, but nothing forces it to avoid hitting a hard limit at the
  currently-spec'd race length. Same "premature" reasoning as ADR-0012's own Alternative 2 —
  revisit if `COMPACT_BATCH_SIZE`, segment length, or race-length assumptions change in practice.

### Alternative 2: Drop monologues from segments entirely, keep no highlight at all

- **Pros**: Simplest possible change — `render_segment` loses its trailing quote and nothing
  replaces it; no `latest_highlight` field, no extra `Checkpoint` field.
- **Cons**: Loses the persona's in-character voice from the summary entirely — the LLM would see
  only dry facts ("found no books, felt strong, ate 4x") about its own past, never a trace of
  what it was actually thinking.
- **Why not**: The monologue is part of what gives the LLM continuity of character, not just
  events — CLAUDE.md's memory design exists partly so the runner "can't reason about 'wtf
  happened before' without it." Keeping exactly one recent monologue costs almost nothing (it's
  replaced, not accumulated) and preserves that.

## Consequences

### Positive

- Post-window-fill growth slope drops by roughly the monologue's share of segment bytes
  (~70-80%), bringing the projected end-of-race input size from ~122K tokens down to
  roughly ~30-37K tokens.
- `latest_highlight` structurally cannot accumulate — a new regression test
  (`test_compact_if_needed_highlight_never_accumulates_across_many_folds`) asserts exactly one
  quoted monologue exists after 40 ticks/20 folds, guarding against this same bug shape
  recurring (see ADR-0012's original one-line-per-tick bug).
- `render_segment`/`render_highlight`/`compact_segment` stay pure, deterministic, and
  independently jumbled per ADR-0017 — no change to that mechanic's guarantees.

### Negative

- `Checkpoint.summary_text` is gone, replaced by `summary_body` + `latest_highlight`. Old
  checkpoint rows are not migrated — accepted as fine since these are dev/test rows
  (`smoke_test.db`), not real race data worth preserving.
- Every monologue except the single most recent one is now permanently lost from the summary
  once its segment is superseded by the next fold — a deliberate trade (see Alternative 2's
  rejection), not an oversight, but worth remembering if a later feature wants "what did the
  runner say 10 hours ago" to actually work.
- Cost/latency per call still climbs monotonically for the entire race, just at a much gentler
  slope than before this change — this ADR does not flatten the curve, only lowers it (see
  Alternative 1).

### Risks

- Risk: the 70-80% monologue-share figure comes from one 75-minute sample at low sleep debt,
  before ADR-0017's jumbling degrades text further. Mitigation: revisit the projected ~30-37K
  ceiling once a real longer run (or a full 60h run, once `FULL_RACE_MINUTES` is actually used
  end-to-end) gives real late-race numbers, same spirit as ADR-0012's own tuning-constant caveat.
