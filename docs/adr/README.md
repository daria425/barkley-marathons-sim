# Architecture Decision Records

| ADR                                                    | Title                                          | Status   | Date       |
| ------------------------------------------------------- | ----------------------------------------------- | -------- | ---------- |
| [0001](0001-defer-sleep-debt-hallucinations.md)          | Defer sleep-debt hallucination events past v1  | accepted | 2026-09-17 |
| [0002](0002-pure-sim-state-composed-into-pydantic-wire-models.md) | Pure sim state composed into Pydantic wire models | accepted | 2026-09-17 |
| [0003](0003-explicit-rng-injection-for-randomness.md)    | Explicit `rng` injection, never global `random.*` | accepted | 2026-09-17 |
| [0004](0004-bonk-push-collapse-mechanic.md)               | Sustained max-effort push through a bonk forces collapse | accepted | 2026-09-17 |
| [0005](0005-vertical-llm-smoke-test-before-course.md)     | Vertical LLM smoke-test slice before building `course.py` | accepted | 2026-09-17 |
| [0006](0006-langfuse-anthropic-instrumentor-ordering-and-create-over-parse.md) | Langfuse via AnthropicInstrumentor — call ordering, and `.create()` over `.parse()` | accepted | 2026-09-18 |
| [0007](0007-vertical-slice-first-across-all-phases.md)    | Build a sped-up vertical slice through every phase before "letting it rip" | accepted | 2026-09-18 |
| [0008](0008-deterministic-code-based-memory-compaction.md) | Deterministic code-based memory compaction, not an LLM summarization call | accepted | 2026-09-18 |
