# ADR-0017: Sleep-debt hallucinations — free-text `Observation.hallucination` plus jumbled compaction memory

**Date**: 2026-09-25
**Status**: accepted
**Deciders**: Daria

## Context

ADR-0001 deferred sleep-debt hallucinations until `Observation`, navigation, and
`agents/memory.py` existed to receive them — all now true. ADR-0008 explicitly named this as the
mechanic it unlocks: "a structured, code-owned summary can be deliberately degraded
(dropped/reordered/misattributed facts, faded monologue lines) as sleep debt rises."
`Observation.hallucination: str | None` has existed on the schema since early on but was never
populated or rendered.

## Decision

Two independent mechanics, both gated by a single `sim/hallucinations.py:severity(elapsed_min)`
curve — reusing `elapsed_min` as the fatigue proxy (no new physiology state, same pattern as
`believed_position`'s existing "no sleep_debt field yet" noise): (1) `roll(elapsed_min, rng)`
fires a per-tick chance of a curated, free-text hallucination line (bear sightings, phantom
conversations, mirages — fully-formed prose, not templated, since it's meant to read as
genuinely left-field), independent of `Observation.event`; (2) `jumble_text(text, severity)`
deterministically garbles a compacted memory segment's rendered prose — word-swaps, digit
misattribution, dropped words — applied once, at fold time, seeded from a stable hash of the
segment's own text (not Python's randomized `hash()`), keeping compaction pure (ADR-0008) and
resume bit-exact (ADR-0009). Because jumbling only touches a segment at the moment it's folded,
a runner's summary reads clean for the early race and degrades only toward however far along
sleep debt was when each chunk was folded — the sliding-window verbatim turns are never touched.
`RunnerState` gained `last_hallucination`, mirroring `last_event`'s wire treatment (regenerated
`api.d.ts`, `raceSlice.ts`'s `hallucinations` map) — no UI rendering yet. Onset/ramp thresholds
are named constants (`HALLUCINATION_ONSET_MIN`/`HALLUCINATION_RAMP_MIN`) set low for dev-slice
testing rather than CLAUDE.md's literal "~40h" target, with the real values commented alongside
for when full-length races start running.

## Alternatives Considered

### Alternative 1: Boolean hallucination flag instead of free text

- **Pros**: simpler schema, could template a response.
- **Cons**: loses exactly the "completely left-field" quality that makes it funny — a bool needs
  a template bank anyway, and the field is already typed as free text.
- **Why not**: kept `str | None` as originally specified; hallucination lines are curated prose
  fed straight into the prompt.

### Alternative 2: Re-jumble the entire summary on every compaction cycle

- **Pros**: summary severity always reflects current elapsed time, not fold time.
- **Cons**: compounding corruption — re-jumbling an already-jumbled string every cycle degrades
  it unboundedly, and jumbling text that was folded before onset would retroactively corrupt
  otherwise-accurate early memory.
- **Why not**: jumble once, at fold time, using that segment's own end-of-segment severity —
  bounded, and produces the more thematically apt "early race is clear, later race is hazy"
  shape for free.

### Alternative 3: Thread the live sim `Random` into compaction for jumbling

- **Pros**: reuses the existing rng-injection convention (ADR-0003) directly.
- **Cons**: `compact_if_needed`/`compact_segment` are called from `_compact_and_checkpoint`,
  which only has a frozen `rng_state` snapshot, not a live generator; consuming draws from a
  reconstructed copy would need care not to look like it's advancing the "real" sequence.
- **Why not**: seeding from a stable hash of the segment's own text keeps `jumble_text` a pure
  function of its inputs with zero rng threading — simpler, and satisfies ADR-0008's
  "deterministic given the same inputs" bar more directly.

## Consequences

### Positive

- No new physiology state — `elapsed_min` (already on `PhysiologyState`) is reused as the
  fatigue proxy, keeping `physiology.py` untouched per ADR-0001's original reasoning.
- Compaction stays pure and testable: `jumble_text` needs no rng argument at all, just
  `(text, severity)`.
- The two mechanics compose independently — a runner can find a book, trip, and hallucinate a
  bear in the same tick, or none of the above; nothing gates on anything else.

### Negative

- Onset/ramp thresholds and per-tick chance are eyeballed dev-testing constants, not tuned
  against real ultrarunning sleep-deprivation data — same caveat as the special-event
  probabilities in ADR-0016.
- `jumble_text`'s specific corruption mix (word-swap/digit-misattribution/dropout weights) is a
  first pass, not validated for "reads funny vs. reads broken" balance.

### Risks

- Digit misattribution can corrupt facts the LLM might otherwise rely on (e.g. a wrong book
  count in old summary text) — intentional per ADR-0008's "misattributed entries" language, but
  worth watching in practice for whether it actually degrades decision quality rather than just
  reading as funny/unreliable narration.
- Since jumbling happens at fold time based on that segment's own elapsed time, a segment folded
  right at the onset boundary could look inconsistent in severity from its neighbors — a minor
  continuity wrinkle, not a bug.
