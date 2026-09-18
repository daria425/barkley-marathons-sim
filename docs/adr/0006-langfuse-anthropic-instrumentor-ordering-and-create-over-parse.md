# ADR-0006: Langfuse via AnthropicInstrumentor — call ordering, and `.create()` over `.parse()`

**Date**: 2026-09-18
**Status**: accepted
**Deciders**: Daria

## Context

CLAUDE.md calls for Langfuse tracing of Anthropic calls from v1 onward. The current Python
integration path (confirmed against live Langfuse docs, not recalled from training) is
`opentelemetry-instrumentation-anthropic`'s `AnthropicInstrumentor`, which patches the SDK to
emit OTel spans, plus Langfuse's `get_client()`. Wiring this in for the ADR-0005 smoke test
surfaced two failures that weren't obvious from the docs and had to be found empirically by
sending a real call and checking whether a trace actually landed:

1. Calling `AnthropicInstrumentor().instrument()` **before** `get_client()` silently traced to
   nowhere — `auth_check()` still returned `True` and the script exited 0, no error anywhere,
   but the Langfuse project stayed empty. `get_client()` is what registers Langfuse's OTel
   `TracerProvider` globally; instrumenting before that exists means the instrumentor's spans
   have nothing to attach to.
2. `agents/participant.py` originally used `client.messages.parse(output_format=Decision)` —
   the documented "recommended" structured-outputs helper. It worked functionally (returned a
   valid `Decision`) but **never produced a trace**, while the exact same call shape via
   `client.messages.create(..., output_config={"format": {"type": "json_schema", ...}})` did.
   `AnthropicInstrumentor` (0.62.3) instruments `.create()` only, not `.parse()`.

Both failures were silent — no exception, no log line, nothing in the script's own output
suggested tracing wasn't working. The only way to catch them was to make a real call and query
Langfuse's API directly (`langfuse-cli api observations-v2 list`) after each change.

## Decision

1. Call order in `scripts/smoke_test.py`: `load_dotenv()` → `get_client()` →
   `AnthropicInstrumentor().instrument()` → only then import anything that constructs an
   Anthropic client (`sim.loop`, transitively `agents.participant`).
2. `agents/participant.py`'s `complete()` uses `messages.create()` with a raw
   `output_config={"format": {"type": "json_schema", "schema": Decision.model_json_schema()}}`
   (schema patched with `"additionalProperties": False`), not `messages.parse()`. Same
   structured-output guarantee, but on the code path that's actually observable.

## Alternatives Considered

### Alternative 1: Keep `.parse()`, accept untraced brain calls for now

- **Pros**: less code (no manual `json.loads` + `Decision.model_validate`), matches the
  Anthropic docs' stated "recommended" pattern.
- **Cons**: the single most important call in the whole system — the one CLAUDE.md explicitly
  requires tracing for — would be invisible in Langfuse. Defeats the purpose of wiring
  tracing in at all.
- **Why not**: tracing the brain call is the entire point; a "recommended" SDK helper that
  can't be observed isn't recommended for this project.

### Alternative 2: Switch to manual OTel span creation around `.parse()` instead of switching call shape

- **Pros**: could keep `.parse()`'s convenience.
- **Cons**: means hand-rolling span attributes (model, tokens, cost) that `AnthropicInstrumentor`
  gives for free on `.create()` — more code, more places to get the Langfuse data model wrong.
- **Why not**: `.create()` + raw schema is barely more code than `.parse()` and gets full
  auto-instrumentation for free.

## Consequences

### Positive

- Every brain call is now a real Langfuse generation, grouped by `session_id=runner_id` and
  tagged `barkley-smoke-test`, confirmed via the CLI against the live project.
- The two failure modes here are now documented — anyone adding a new Anthropic call site
  (e.g. the phase-2 autocompaction LLM call in `agents/memory.py`) knows to use `.create()`
  and to check the call-ordering constraint, instead of rediscovering both the hard way.

### Negative

- `complete()` does its own `json.loads`/`Decision.model_validate` instead of getting a typed
  `parsed_output` for free — marginally more code in `Participant.decide()`.
- Tied to `opentelemetry-instrumentation-anthropic`'s current instrumentation coverage; if a
  future SDK version starts instrumenting `.parse()`, this ADR's constraint could be revisited
  (but there's no cost to leaving it as-is either).

### Risks

- Risk: a future contributor adds a new Anthropic call via `.parse()` (following the "official
  recommended" docs) and silently loses tracing again. Mitigation: this ADR + the docstring on
  `agents/participant.py`'s `complete()`.
