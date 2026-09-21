# ADR-0011: v1's FastAPI + WebSocket surface wired via an optional `on_update` callback

**Date**: 2026-09-21
**Status**: accepted
**Deciders**: Daria, Claude

## Context

CLAUDE.md's v1 API surface calls for a REST endpoint to start a run plus a WebSocket
streaming live `RaceState`/`RunnerState` and brain-call/monologue events, with multiple
clients able to watch at once (frontend is the next likely phase). `sim/loop.py`'s
`run()`/`think()` already existed as a self-contained async loop (ADR-0005/0009) exercised
directly by `test_resume.py` with no FastAPI involved. Also found: the pre-existing
`main.py` stub called `load_dotenv()`/`get_client()`/`AnthropicInstrumentor().instrument()`
inside a request handler, *after* `sim.loop` (and transitively `agents.participant`, which
builds its `AsyncAnthropic` client at import time) was already imported at module load — so
the API key was never in the environment when the client was constructed.

## Decision

`sim/loop.py` gains an optional `on_update: Callable[[RaceState], Awaitable[None]] | None =
None` parameter on `run()`/`think()`, defaulting to `None`. `main.py` owns a
`set[WebSocket]` and passes a `_broadcast` closure as `on_update` when it calls `run()` from
`POST /run`; `sim/loop.py` itself never imports FastAPI or knows a WebSocket exists. The
dotenv/Langfuse/instrumentor setup is extracted into `observability.py`'s
`setup_observability()`, called at the top of `main.py` (and `scripts/smoke_test.py`)
*before* `sim.loop` is imported — a FastAPI startup/lifespan hook can't fix the ordering bug
since that still runs after module-level imports complete.

## Alternatives Considered

### `sim/loop.py` imports FastAPI/a connection manager directly

- **Pros**: one less indirection layer.
- **Cons**: couples the pure sim loop to a specific web framework.
- **Why not**: breaks `test_resume.py`'s framework-free testing of
  `advance_tick`/`restore_state`, and CLAUDE.md already separates `sim/` (pure) from
  `main.py`/API concerns.

### `asyncio.Queue` between loop and API instead of a direct callback

- **Pros**: decouples producer/consumer further, natural backpressure point.
- **Cons**: adds buffering/consumer-loop complexity.
- **Why not**: v1's single-runner, single-run scope doesn't need it yet; a callback is
  simpler and sufficient (ADR-0007's vertical-slice-first).

### REST polling instead of WebSocket push

- **Pros**: simpler client implementation.
- **Cons**: doesn't match the "watch it run live" experience.
- **Why not**: CLAUDE.md's v1 API surface explicitly specifies WS push, not a polling
  endpoint.

## Consequences

### Positive

- `sim/loop.py` stays framework-agnostic and directly testable; CLI/smoke-test/
  `test_resume.py` paths are unaffected (`on_update=None`).
- Multiple WS clients supported for free — `_broadcast` fans out to a set, dropping dead
  connections without affecting the sim.
- Fixes the real import-ordering bug in the original stub.

### Negative

- `RaceState` gets built in two places (`run()`'s per-tick loop and `think()`'s
  post-decision path) via shared `_build_runner_state`/`_build_race_state` helpers — minor
  duplication of call sites, not logic.

### Risks

- `on_update` is `await`ed synchronously inside the tick loop; a slow client's `send_text`
  could stall ticking. Mitigated today only by per-client try/except (a dead/erroring
  client is dropped, not retried) — acceptable at v1's dev-loop scale, but worth revisiting
  if/when the frontend is a real consumer under sustained load.
