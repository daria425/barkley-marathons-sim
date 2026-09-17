# ADR-0001: Defer sleep-debt hallucination events past v1

**Date**: 2026-09-17
**Status**: accepted
**Deciders**: Daria

## Context

CLAUDE.md's physiology spec lists sleep-debt-driven hallucination events (past ~40h elapsed, a random chance of a hallucination injected into the runner's Observation) alongside the other physiology mechanics (HR, glycogen, hydration, core temp). While implementing `physiology.py`, we reached this item and reconsidered its scope: hallucinations aren't really a body-state number like glycogen — they mostly manifest downstream, muddling navigation (false landmarks, jumbled believed-position reasoning) and the LLM's own narrative context (jumbling past events, false memories in the monologue). That's a different kind of concern than the pure numeric steppers already in physiology.py — it touches `Observation` construction, `agents/memory.py`'s sliding window/autocompact, and possibly navigation noise, not just physiology state.

## Decision

Leave sleep-debt hallucination events out of the v1 physiology pass. `physiology.py` ships with HR, glycogen, hydration, core temp, bonk pace collapse, and the bonk-push/collapse mechanic (ADR pending separately if warranted). Hallucinations get designed once `Observation`, navigation, and `agents/memory.py` exist to receive them — implementing the trigger now would mean guessing at an interface those later phases haven't defined yet.

## Alternatives Considered

### Alternative 1: Implement a hallucination flag/chance in physiology.py now

- **Pros**: Checks the box in CLAUDE.md's physiology list; keeps all "body state" mechanics in one PR.
- **Cons**: Hallucination's actual effect lives in Observation/navigation/memory, none of which exist yet — physiology.py would end up owning a stub with no consumer, or we'd guess at the interface and likely rework it once memory.py is designed.
- **Why not**: Premature — no downstream code to plug it into yet, and the "what does a hallucination actually do" design question is bigger than a physiology stepper.

## Consequences

### Positive

- `physiology.py` stays scoped to genuine numeric body state; easier to keep pure and property-tested without a fuzzy "narrative" concern mixed in.
- Hallucination design gets deferred to when `Observation`/`agents/memory.py` exist, so it can be designed against real interfaces instead of guessed ones.

### Negative

- CLAUDE.md's physiology section technically isn't fully implemented yet — this ADR is the record of why, so it doesn't read as silently dropped scope.

### Risks

- Risk: forgetting to revisit this once `agents/memory.py` exists. Mitigation: this ADR is the tracking marker; re-check when starting the memory/persistence phase (CLAUDE.md's phase 2) or when building `agents/brain.py`'s Observation construction in phase 1.
