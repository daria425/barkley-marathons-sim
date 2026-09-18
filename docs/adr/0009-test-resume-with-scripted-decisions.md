# ADR-0009: Test resume-from-checkpoint with scripted decisions, not the live LLM

**Date**: 2026-09-18
**Status**: accepted
**Deciders**: Daria

## Context

After wiring `db.load_checkpoint` into `sim/loop.py`'s `run()` (built in ADR-0008 but never
actually called), resume needed a way to verify it reconstructs the *same continuation* a
never-interrupted race would have had, not just "it loads without crashing." The real brain
call (`agents/participant.py`'s `Participant.decide`) is non-deterministic and costs a real API
call, so it can't be used to assert bit-exact continuation, and using it in a test would make
the suite slow, flaky, and costly to run in CI.

## Decision

`sim/loop.py`'s tick logic is refactored into pure, decision-driven functions — `LoopState`,
`build_initial_state`, `restore_state`, `advance_tick` — decoupled from the async
brain-calling wrapper. `tests/test_resume.py` drives a reference run and a
checkpoint-then-resume run with an identical **scripted, fixed list of `Decision` objects**,
then asserts the resulting `PhysiologyState`/`FrozenHeadStatePark` and subsequent RNG draws are
identical — proving resume preserves ADR-0008's bit-exact-RNG requirement, independent of
whatever the LLM would have actually decided. One test round-trips the checkpoint through real
`db.save_checkpoint`/`load_checkpoint` (SQLite); the other stays purely in-memory. Also verified
manually: ran `sim/loop.py` twice against the same on-disk DB — first run printed "Starting
Hank fresh," second printed "Resuming Hank from checkpoint at elapsed_min=1.0," with
`elapsed_min` and turn counts continuing cumulatively (1.0→2.0, 10→20 turns) rather than
resetting.

## Alternatives Considered

### Alternative 1: Test resume via the real Participant/LLM call

- **Pros**: exercises the actual code path end to end, including the brain call itself.
- **Cons**: slow, costs real API calls on every test run, and non-deterministic — bit-exact
  continuation can't even be asserted since the LLM's own decision varies run to run.
- **Why not**: defeats the purpose of the test, which is to verify the *resume mechanics*, not
  the brain.

### Alternative 2: Stub `Participant.decide()` but still route through the full async
`think()`/`asyncio.create_task` machinery

- **Pros**: closer to a true integration test of the whole loop.
- **Cons**: unnecessary complexity for what's fundamentally a pure state-transition property;
  the async scaffolding itself was already proven separately by ADR-0005's smoke test.
- **Why not**: more moving parts for no added confidence in the thing actually being tested.

## Consequences

### Positive

- Resume correctness is covered by fast, deterministic tests that run in CI with no API key
  or cost.
- The refactor that enabled this (`LoopState`/`build_initial_state`/`restore_state`/
  `advance_tick` as pure functions) makes `sim/loop.py`'s tick logic independently testable
  going forward, not just for resume.
- Caught a real perf bug as a side effect: `_start_coords()` was parsing a 178k-line GPX file
  on every fresh-start call — now more frequent due to these tests — fixed with `lru_cache`
  since the start point never changes.

### Negative

- These tests don't exercise the actual async `think()`/checkpoint-writing path end to end
  (`asyncio.create_task`, the semaphore, `think()`'s exception handling) — that's currently
  only verified by manually running `sim/loop.py` twice, not by an automated test.

### Risks

- A real kill-mid-run integration test (actually terminating the process, not just calling
  functions directly) is still open and not yet built. Mitigation: none yet — noted here so it
  isn't forgotten.
