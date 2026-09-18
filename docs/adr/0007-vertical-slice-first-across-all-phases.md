# ADR-0007: Build a sped-up vertical slice through every phase before "letting it rip"

**Date**: 2026-09-18
**Status**: accepted
**Deciders**: Daria

## Context

ADR-0005 inserted one vertical slice (brain loop before `course.py`) inside phase 1, justified
by "prove the riskiest thing works before building around it." Having watched that work — a
sped-up, stubbed, throwaway-parts-and-all slice caught two real bugs (a day-rollover bug in
clock formatting, and two silent Langfuse tracing failures) faster than building each phase to
completion in isolation would have — the same reasoning generalizes past phase 1: keep every
phase (persistence, multi-persona, and even the frontend) built as a small, fast, end-to-end
slice first, and only expand any one piece to full scope once the whole chain already runs.

## Decision

Development keeps running at dev speed (sped-up ticks, short test durations, stubbed pieces
where a later phase will replace them) **across every phase, including the frontend**, until
the entire system — physiology, weather, course/navigation, brain, persistence, multi-persona,
and frontend — runs end to end as a compressed slice. Only after that full chain works does the
project switch to CLAUDE.md's actual target mode: 1x real time, the full 60-hour cutoff, full
persona roster. "Full scope, still fast" comes before "real scope, real speed" — not phase by
phase to 100% before moving on, but the whole system to a thin 100% before any one part goes
deep.

This doesn't change *what* CLAUDE.md's Build order section says gets built or in what
dependency order (course still needs physiology, brain still needs a persona, frontend still
needs a stable API) — it changes the *completeness bar* at each step: a phase is "done enough
to move on" once it works in the compressed slice, not once it's fully fleshed out.

## Alternatives Considered

### Alternative 1: Finish each phase to full scope before starting the next (CLAUDE.md as originally read)

- **Pros**: each phase is genuinely complete when checked off; less risk of forgotten stubs.
- **Cons**: ADR-0005 already demonstrated the opposite risk is worse in practice — building
  `course.py` to completion before testing the brain loop would have meant discovering
  prompt/parsing/persona problems only after a much bigger investment. The same argument
  applies to building the full frontend against an API that persistence/multi-persona haven't
  stress-tested yet.
- **Why not**: the cheapest time to find an integration problem is when the least has been
  built around it — true within phase 1, and just as true across phases.

### Alternative 2: Skip straight to full real-time (1x, 60h) once the vertical slice works

- **Pros**: matches CLAUDE.md's stated target experience sooner.
- **Cons**: a 60-hour full-scope run is an extremely expensive way to discover a bug that a
  60-second compressed run would have caught in seconds.
- **Why not**: CLAUDE.md's own "Speed multiplier is a dev convenience" bullet already says
  dev-speed iteration is the intended workflow; this ADR just extends that instinct past
  phase 1 to the whole build.

## Consequences

### Positive

- Every phase gets its riskiest assumptions checked against a real (if compressed) end-to-end
  run before time is sunk into fleshing it out — same payoff ADR-0005 already delivered once.
- The frontend gets built against a system that's already been proven to work, not against a
  backend that's only ever been unit-tested in isolation.

### Negative

- "Done" for any given phase is fuzzier than a clean per-phase completion checklist — requires
  judgment about when a slice is thin-but-real versus so stubbed it's not actually testing
  anything.
- Full real-time behavior (sleep debt over 40h, cardiac drift over a real ultra's duration,
  actual cutoff pressure) can't be observed until the very end — some bugs may only surface
  then, later than a full-depth-per-phase approach would have found them.

### Risks

- Risk: stubs accumulate across phases and the "final let it rip" step turns into a much
  bigger integration effort than expected. Mitigation: each phase's ADR (like ADR-0005) names
  its stubs explicitly, and CLAUDE.md's Build order section is the checklist for what still
  needs replacing before the real run.
