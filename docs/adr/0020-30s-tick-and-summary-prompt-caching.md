# ADR-0020: 30-second ticks (`TICK_DT_MIN = 0.5`) and prompt caching on the summary

**Date**: 2026-09-30
**Status**: accepted
**Deciders**: Daria

## Context

Ahead of the first full-scale run (`speed=1`, `duration_min=3600`), cost was estimated from real
prod turns (`count_tokens`): ~6.7k fixed prompt tokens per call plus ~54 tokens per summary
segment, with one segment per `COMPACT_BATCH_SIZE` (20) calls. With a call every 15s tick
(14,400 calls) the average call is ~26k input tokens and the race costs ~$390 on Haiku 4.5 — and
because summary growth is per-call, cost is roughly quadratic in call count. Nothing was cached.
Rate limits are not a constraint (10M input tokens/min).

## Decision

1. `TICK_DT_MIN` goes from 0.25 to **0.5** sim-min (30 real seconds at 1x). Brain calls stay
   **per tick** (ADR-0015 unchanged in that respect), so there is still no call scheduler and no
   dropped `Observation.event`. A 60h race is 7,200 ticks/calls.
2. Per-tick event chances (`TRIP`/`PUDDLE`/`BRIAR`/`WILDLIFE`/`BOTTLE_DROP`, and
   `HALLUCINATION_MAX_CHANCE_PER_TICK`) are **doubled** so the per-sim-hour rate, and so the
   number of comedy events per race, is unchanged. They remain unscaled-by-dt constants.
3. `Participant.build_prompt` puts `cache_control: ephemeral` on the summary message, making
   system prompt + summary a cached prefix. Both are byte-identical between folds; the sliding
   window after them changes every tick and stays uncached.

## Alternatives Considered

### Alternative 1: Decouple brain calls from ticks (call every Nth tick)

- **Pros**: keeps the 15s sim tick and its smoother WS updates.
- **Cons**: an `Observation.event` on a skipped tick would never reach the LLM unless events are
  accumulated — new mechanism, new failure surface.
- **Why not**: rejected in favor of just making the tick coarser; ADR-0015's "no scheduler" stands.

### Alternative 2: Scale event chances by `dt_min` at the roll site

- **Pros**: `TICK_DT_MIN` could change freely afterward.
- **Cons**: touches `course.py`/`hallucinations.py` and their tests for a value that is fixed.
- **Why not**: not worth it while the tick is a constant; the comment in `sim_constants.py`
  records that changing it again means re-scaling.

### Alternative 3: Leave event chances alone

- **Pros**: zero change.
- **Cons**: half as many events per race and per real-time minute.
- **Why not**: the comedy density is the point of the sim.

## Consequences

### Positive

- Estimated full-race cost ~$390 -> ~$125 (tick change alone) -> ~$60 (with caching). Verified
  live: a 9,135-token prefix was written once and read from cache on the next two calls.
- Half the brain calls, half the summary segments, half the Langfuse traces.

### Negative

- The runner acts on information up to 30s old, and `SLIDING_WINDOW_N`/`COMPACT_BATCH_SIZE` (20
  turns) now span 10 sim-minutes instead of 5.
- Weather (`step_weather`, per-tick and unscaled) holds for twice as long in sim-time, and
  eat/drink refills (flat per tick) give half the refill per sim-minute to a runner that
  eats/drinks every tick. Left as-is deliberately.

### Risks

- ADR-0015's "the runner cannot skip a book" bound is now `0.5 / 5 = 0.1km` per tick at the pace
  floor (5 min/km), twice the old `BOOK_PROXIMITY_KM` (0.05km), and only the end-of-tick
  position is checked. `BOOK_PROXIMITY_KM` was raised to **0.075km**: a straight pass at
  realistic paces (>= 10 min/km, <= 0.05km per tick) is now caught, and only an edge-of-radius
  pass at the pace floor could still slip through. Books stay ~2.3km apart, so this can't
  cause double finds. A swept-segment distance check would remove the gap entirely; not done.
- Cache misses are silent (billing only). Check `usage.cache_read_input_tokens` in Langfuse on the
  first live run.
