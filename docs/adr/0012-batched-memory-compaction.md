# ADR-0012: Batch memory compaction instead of folding one turn per tick

**Date**: 2026-09-22
**Status**: accepted
**Deciders**: Daria

## Context

While reviewing what breaks running v1 at 1x/60h (the actual target per CLAUDE.md — currently
stubbed short by `TOTAL_SIM_MINUTES` in ADR-0005's smoke-test loop), a bug surfaced in how
`sim/loop.py`'s `_compact_and_checkpoint` drives ADR-0008's compaction. It calls
`agents/memory.py`'s `compact_if_needed` on every tick once turn count exceeds
`SLIDING_WINDOW_N` (20), passing the *entire* turn history each time. That function re-derived
and re-appended a summary of the whole aged-out prefix on every call instead of just the
newly-aged turns, so the running summary grew by one redundant, overlapping, full-range line
per tick — forever. Over a 60h/14,400-tick race that's ~14,380 lines (~1.7MB), with per-call
prompt cost climbing roughly linearly with elapsed race time and eventually exceeding Haiku
4.5's 200K context window outright — which, per CLAUDE.md's "no retries, keep the old decision"
contract, would silently freeze the runner with no visible error partway through the race.

## Decision

Decouple "how much recent detail the LLM sees verbatim" (`SLIDING_WINDOW_N`, unchanged at 20)
from "how coarse/how often compaction folds old turns into the summary" (new
`COMPACT_BATCH_SIZE`, 20). `compact_if_needed` now takes an explicit `folded_count` high-water
mark from the caller — persisted via a new `Checkpoint.summary_folded_count` field for correct
resume — and only folds once `COMPACT_BATCH_SIZE` new turns have aged out past the window,
folding all of them into **one** segment line at once rather than one line per tick. Turns that
have aged out of the verbatim window but haven't yet reached a full batch are simply not in the
prompt yet (a bounded blind spot of at most `COMPACT_BATCH_SIZE - 1` turns — a few sim-minutes
at `TICK_DT_MIN=0.25`, negligible against a 60h race).

## Alternatives Considered

### Alternative 1: Naive delta-fix, no batching

- **Pros**: Smallest possible change — fold exactly the one newly-aged turn each tick instead
  of re-deriving the whole prefix.
- **Cons**: Removes the redundancy but not the unbounded growth: the summary still gains one
  line per tick for the entire race, ~14,380 lines by hour 60.
- **Why not**: Fixes the bug's symptom (redundant re-summarization) but not its consequence
  (unbounded linear growth over a 60h race).

### Alternative 2: Recursively re-compact the summary text itself past a size threshold

- **Pros**: Caps summary size regardless of race length or batch size; works even if batching
  alone isn't enough headroom.
- **Cons**: A second compaction pass with its own trigger/threshold logic to design and test,
  on top of the one this ADR already adds.
- **Why not**: Premature — batching alone gives ~20x headroom (see Consequences), and nothing
  has shown that isn't enough for a 60h race. Revisit if it turns out not to be.

### Alternative 3: Raise `SLIDING_WINDOW_N` instead of adding a separate batch size

- **Pros**: One knob instead of two; Haiku 4.5's 200K context can easily afford a much larger
  verbatim window.
- **Cons**: Conflates two different concerns — how much recent detail informs the *next*
  decision vs. how coarse the compacted history gets — and doesn't by itself bound total summary
  growth over a 60h race; the same per-tick-fold bug would just trigger later.
- **Why not**: Doesn't solve the actual problem, just delays it.

## Consequences

### Positive

- Total summary growth over a 60h/14,400-tick race drops from ~14,380 lines to ~720 (batch
  count = race length / `COMPACT_BATCH_SIZE`), keeping per-call prompt cost roughly flat over
  the race instead of climbing linearly toward a context-window failure.
- The two compaction concerns (verbatim recency vs. summary coarseness) are now independently
  tunable constants (`SLIDING_WINDOW_N`, `COMPACT_BATCH_SIZE`) instead of one value serving both
  jobs.
- Resume stays bit-exact: `Checkpoint.summary_folded_count` (default `0`, so old checkpoints
  without it just start pending-count from scratch rather than erroring) lets a resumed run
  pick up mid-batch instead of re-folding or losing already-folded turns.

### Negative

- Turns within a not-yet-full batch are briefly absent from both the verbatim window and the
  summary — up to `COMPACT_BATCH_SIZE - 1` turns' worth of detail (a few sim-minutes) is
  invisible to the LLM until that batch completes. Accepted as negligible against race length.

### Risks

- Risk: `COMPACT_BATCH_SIZE=20` was picked to match `SLIDING_WINDOW_N`'s existing value for a
  simple first pass, not derived from a target summary-size ceiling. Mitigation: revisit if a
  real 60h run (once `TOTAL_SIM_MINUTES` is no longer stubbed short) shows ~720 lines is still
  too much, or too coarse — this is a tuning constant, not a documented spec, same as
  `SLIDING_WINDOW_N` itself.
