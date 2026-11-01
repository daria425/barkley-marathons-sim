# ADR-0025: "You just ate" wording, a drink counter, realistic drain, and dehydration

**Date**: 2026-11-01
**Status**: accepted
**Deciders**: Daria

## Context

The first `study-01` Haiku run (60 sim-min, speed 20) ate on 79 of 120 decisions and drank on 77,
ending at 100% glycogen and hydration. In 71 calls it saw "Last ate 0 min ago" and ate again,
reasoning "Ate zero minutes ago so I need calories": it read 0 as "haven't eaten". Two things
locked that in. `_build_observation` rounded the counter, and Python's `round(0.5)` is 0, so the
tick after an eat still read 0. The model's own earlier monologues, replayed in the sliding
window, repeated the line. Drinking had no counter at all.

Underneath that, the drain rates made fuelling irrelevant: glycogen drained `effort * 0.5` %/h
(effort 5 took ~32h to reach the 20% bonk line with no food) and hydration `1 + 0.3 * heat` %/h.

## Decision

- **Wording, not enforcement.** `format_observation` says "You just ate." under 1 sim-minute,
  "You last ate N min ago." (floored) after that, and "You haven't eaten since the start." before
  the first eat. Same for drinking ("You just drank.", "You haven't drunk anything since the
  start.").
- **Drink counter.** `Observation`, `Checkpoint` and `LoopState` gain `last_drank_min_ago`. Both
  counters are `float | None`: the raw value, not rounded, and `None` until the first eat/drink.
  `sim/loop._minutes_since` advances them.
- **Drain rates** (named constants in `sim/physiology.py`): glycogen `6 * effort` %/h, so an unfed
  runner bonks after ~1h20 at effort 10 and ~2h40 at effort 5; hydration `10 + 4 * heat` %/h.
  Refill amounts (+15% per eat, +20% per drink) are unchanged. `tests/test_physiology_reference.py`
  pins these against rough real ranges; the property tests are unchanged and still pass.
- **Dehydration.** Hydration had never reached the model or affected the body; only the watch
  face showed it. `Observation.thirst` (`physiology.describe_thirst`) reads "not thirsty",
  "thirsty" (<60%), "dry mouth, head pounding" (<40%), "dizzy, badly dehydrated" (<20%).
  `compute_pace` slows pace ×1.3 below 40% and ×1.6 below 20%, stacking with a bonk.
- **Pace floor moved.** `compute_pace` applied its fastest-pace floor after the bonk penalty, so at
  effort 10 a bonk never slowed the runner. The floor now applies to the effort pace before the
  bonk and dehydration penalties.

## Alternatives Considered

### Alternative 1: Enforce a cooldown between eats

- **Pros**: caps intake no matter how the model reads its observation.
- **Cons**: hides the real bug (a misleading prompt) behind a rule; needs a "stomach full" message.
- **Why not**: Daria judged the misreading to be the core issue. Still an option if models keep
  over-eating with the clearer wording.

### Alternative 2: Keep the integer field and only special-case 0 in the prompt

- **Pros**: no data-contract change.
- **Cons**: rounding already turned 0.5 into 0, and 0 can't distinguish "just ate" from "never ate".
- **Why not**: `None` plus the raw float says both things exactly.

## Consequences

### Positive

- The model is told plainly that it just ate or drank, and is told when it never has.
- Bonking and dehydration are reachable in a real run, and both slow the runner, so eating
  and drinking decisions now matter.

### Negative

- Every v1 physiology number changes; old runs aren't comparable on glycogen/hydration.
- Old checkpoints don't load (`last_drank_min_ago` is required); wipe the DB, as with ADR-0024.

### Risks

- Dehydration only affects pace, not HR or core temp; revisit if it reads as too mild.
- An eat still adds +15% on every tick it's chosen, so a model that keeps choosing to eat can
  still top up for free.
