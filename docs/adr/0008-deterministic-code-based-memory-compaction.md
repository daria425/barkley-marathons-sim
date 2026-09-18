# ADR-0008: Deterministic code-based memory compaction, not an LLM summarization call

**Date**: 2026-09-18
**Status**: accepted
**Deciders**: Daria

## Context

CLAUDE.md's "Memory and persistence" section specifies that when sliding-window history exceeds
N turns, "an LLM call (not code) compresses the aged-out objects into the summary — similar to
chatbot context autocompaction... costs an extra call per compaction but reads as a coherent
narrative rather than a stats dump." Revisiting this while designing phase 2 (persistence +
resume, right after v1 per CLAUDE.md's build order): an LLM-based compactor is a second async
LLM failure surface living inside exactly the subsystem responsible for surviving a 60-hour run
without losing state, and it can't be property-tested the way `physiology.py`'s hard requirement
demands. Since Observation/Decision history is already fully structured (logged verbatim to
SQLite), a code-based compactor can extract the same information deterministically.

## Decision

Replace the planned LLM autocompaction call with a deterministic, code-based (templated)
compaction step in `agents/memory.py`, triggered the same way CLAUDE.md originally specified
(`turn_count > SLIDING_WINDOW_N`) — the trigger condition doesn't change, only what happens on
it. On trigger, the oldest `turn_count - N` turns are folded as one segment into the running
summary string (not batched into fixed-size chunks — simplest option, and the window only
briefly holds slightly more than N between compactions in exchange).

Per segment, extract from the raw Observation/Decision objects:

- elapsed-minute range and loop number covered
- books found in the segment
- dominant `feel` value and whether bonking/collapse occurred
- eat/drink counts and total `rest_min`
- whether `quit=True` appeared in any decision, even if it didn't stick
- one representative monologue line (the most "eventful" turn in the segment — first bonk, a
  book find, a fall)

These get rendered through a template into 1–2 prose sentences appended to the summary (e.g.
"Miles 8–14 (hour 6–9): found 1 book, ate twice, started bonking around mile 12. 'god my quads
are done for' — kept pushing at effort 7 anyway."), not concatenated as a raw stats dump.

This composes with resume: the same summary text is one field of the per-runner `Checkpoint`
(see `db.py`'s new `checkpoints` table), stored as an `INSERT OR REPLACE` row keyed by
`runner_id`, rewritten on every brain decision per CLAUDE.md's checkpoint cadence. A checkpoint
holds everything needed to reconstruct `sim/loop.py`'s `run()` local state bit-exactly,
including `rng.getstate()` — confirmed there is exactly one shared `rng` instance across
`sim/loop.py` and `frozen_head_state_park.py` (`physiology.py` takes no rng at all, per its
purity requirement), so only one state blob is needed:

```python
class Checkpoint(BaseModel):
    runner_id: str
    elapsed_min: float
    physio: PhysiologyState
    park: FrozenHeadStatePark
    start_hour: float
    true_pos: tuple[float, float]
    believed_pos: tuple[float, float]
    loop: int
    books_found: int
    last_ate_min_ago: float
    last_decision: Decision
    rng_state: str          # json.dumps(rng.getstate())
    summary_text: str
    summary_covers_up_to_elapsed_min: int
    updated_at: str
```

Built as an isolated, unit-testable slice first (per ADR-0007): compaction and checkpoint
save/load land as standalone functions in `agents/memory.py`/`db.py` with their own tests
(compaction is deterministic given the same turns; a checkpoint round-trips through JSON
including `rng` state) before being wired into `sim/loop.py`'s `run()`.

## Alternatives Considered

### Alternative 1: Keep LLM-based autocompaction as CLAUDE.md originally specified

- **Pros**: Matches the original design; can synthesize genuinely novel connections across the
  compacted window in the persona's own voice (e.g. noticing a repeated mistake) — something a
  template fundamentally cannot do.
- **Cons**: A second untestable, non-deterministic LLM call in the exact path responsible for
  not losing a runner's race; another failure mode needing its own tolerance story on top of the
  existing brain-call one; can't be property-tested.
- **Why not**: The single novel-insight benefit isn't worth trading away determinism and
  testability in the subsystem whose entire job is reliability over a 60-hour run.

### Alternative 2: Hybrid — LLM summary only for very long compacted spans

- **Pros**: Gets narrative richness back for the cases where it'd matter most (very long
  histories).
- **Cons**: Two summarization code paths to maintain and test; added complexity for a benefit we
  haven't earned or needed yet.
- **Why not**: Premature — nothing about the current design has demonstrated the plain
  code-based summary is insufficient.

## Consequences

### Positive

- Compaction becomes property-testable like the rest of the sim's pure logic, not
  eyeball-verified.
- Removes an LLM failure/latency/cost surface from the persistence-critical path.
- Structured, code-owned summaries can be *deliberately* degraded (dropped/reordered/
  misattributed entries, faded monologue lines) as a function of sleep debt or elapsed time —
  this is exactly the hallucination mechanic ADR-0001 deferred pending `Observation`/navigation/
  `agents/memory.py` existing. This ADR is what unlocks it, not scope creep.

### Negative

- Loses the LLM summary's ability to surface novel, persona-voiced connections across the
  compacted window ("I keep making the same mistake") — a template can only ever surface what we
  chose to extract. Accepted as a reasonable cost, not a zero-cost swap.

### Risks

- Risk: a templated summary reads mechanically despite the "still prose" intent. Mitigation:
  design the template with narrative phrasing in mind (per-segment sentences, not a stat block),
  and revisit if it reads flat once real output is seen.
