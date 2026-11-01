# v2: Controlled multi-model study

v1 ran one model (Haiku) through one race whose conditions were deliberately random. v2 turns
that into a **study**: several models run the same persona, the same system prompt and the same
race conditions, so **the model is the only variable that changes**. The LLM's own sampling
variance (temperature 1) is kept on purpose: it's the interesting part.

Status: **plan**. Decisions marked _(decided)_ came from the planning session on 2026-10-30/31;
everything else is a proposal awaiting a go-ahead per CLAUDE.md's plan-per-phase rule.

## Decisions so far

- _(decided)_ **Everything in the sim is fixed, not random.** A `RaceConfig` pins the seed, the
  start hour and the weather. No backwards compatibility with v1's random mode: reverting to
  v1 means `git checkout`, not a runtime flag.
- _(decided)_ **Events and hallucinations stay, but fire at fixed points** instead of being
  rolled per tick.
- _(decided)_ **Full migration to OpenRouter.** No direct Anthropic calls. Claude (Haiku) runs
  through OpenRouter like every other model.
- _(decided)_ **Temperature 1** wherever the provider supports it (same as v1's default).
- _(decided)_ The first v1 Haiku run does **not** need to be reproduced.
- _(decided)_ Frontend shows each model's run as a tile in a grid.

## Phase order

| Phase | What | Why this order |
|---|---|---|
| 1 | Deterministic race (`RaceConfig`) | Prerequisite for any comparison |
| 2 | OpenRouter migration | One client for every model, Haiku included |
| 3 | Multi-runner sim (roster, shared world) | Run N models in one race |
| 4 | Frontend grid | Watch them side by side |
| 5 | Study runs | Repeated runs per model, analysis |

Each phase gets a thin, sped-up slice first (ADR-0007) and its own plan check-in.

---

## Phase 1: Deterministic race

### Every source of randomness in v1, and what replaces it

All of v1's randomness comes from one unseeded `random.Random()` (`sim/loop.py`), passed
explicitly everywhere (ADR-0003).

| v1 source | Where | v2 |
|---|---|---|
| Start hour, random 0–12h | `loop.py` `_resume_or_start` | `RaceConfig.start_hour` |
| Starting weather + Markov weather changes | `frozen_head_state_park.py` `initial_state`, `step_weather` | `RaceConfig.weather` timeline |
| Temperature jitter ±1°C | `compute_temperature` | **removed**: diurnal curve + weather offset only |
| Fog jitter ±5% | `compute_fog_pct` | **removed**: weather + night only |
| GPS noise (direction, offset) | `course.believed_position` | **seeded**, per-tick stream from `RaceConfig.seed` |
| Special events (trip, puddle, briars, wildlife, bottle) | `course.detect_special_event` | `RaceConfig.events` schedule |
| Hallucinations | `hallucinations.roll` | `RaceConfig.hallucinations` schedule |
| Memory jumbling | `hallucinations.jumble_text` | unchanged: already deterministic (sha256 of the text) |
| LLM sampling | `participant.py` | **kept**, temperature 1 |

After this phase the only randomness left in the sim is GPS noise, and that is a pure function
of `(seed, elapsed_min)`.

### Why a plain seed on the shared rng isn't enough

`detect_special_event` only draws numbers on certain terrain or at night, so how many draws a
tick consumes depends on **where the runner is**. Two runs with the same seed that make
different decisions get out of step on the shared rng, and from then on even the weather
differs. That's why v2 drops the shared rng instead of seeding it:

- Weather, events and hallucinations become **schedules**, with no rng at all.
- GPS noise uses a **stream derived per tick**: `Random(f"{seed}:gps:{elapsed_min}")`. Python seeds
  `str` deterministically across processes (unlike `hash()`). Noise at tick 412 is then the
  same in every run with that seed, whatever the runner did before.

Side effect: resume no longer needs `rng.getstate()`. The seed and the elapsed sim-minute rebuild
everything, so `Checkpoint.rng_state` and `db.py`'s rng (de)serialization helpers go away.

### `RaceConfig` (proposed shape)

```python
class WeatherPhase(BaseModel):
    condition: str            # one of sim_constants.WEATHER_CONDITIONS
    duration_min: float

class ScheduledEvent(BaseModel):
    at_elapsed_min: float
    event: EventType          # found_book excluded; that's still position-driven

class ScheduledHallucination(BaseModel):
    at_elapsed_min: float
    text: str

class RaceConfig(BaseModel):
    name: str                 # e.g. "study-01"
    seed: int
    start_hour: float
    weather_cycle: list[WeatherPhase]      # repeats for the whole race
    events: list[ScheduledEvent]
    hallucinations: list[ScheduledHallucination]
```

- _(decided)_ Weather is a **looping cycle**: clear 2h → fog 2h → rain 2h → repeat.
  _(decided)_ Start hour **06:00**.
- LLM temperature is not in Phase 1's `RaceConfig`: it belongs to Phase 2 (OpenRouter), where
  per-model support for it is the open question.
- Lives in a data file, `server/races/<name>.yaml`, like personas: tuning a study shouldn't
  touch Python. `POST /run?race=study-01` selects it. First draft: `server/races/study-01.yaml`.
- The config name **and a hash of its contents** go into every checkpoint and every Langfuse
  trace, so each result says exactly which conditions produced it. Resuming a checkpoint against
  a changed config file is refused rather than silently mixed.

### Fixed-point events: semantics

- **Time-based, not position-based.** An event fires for every runner at the same
  `elapsed_min`, so every model gets the same stimulus at the same moment. Position-based
  triggers (e.g. "at km 12") would hit fast and slow models at different times, and models
  that leave the trail would never reach them.
- **Terrain gating is dropped.** v1 only rolled puddles on creek terrain, briars in briars, and
  so on. A scheduled event fires wherever the runner happens to be. Night-only wildlife still
  works by construction: the start hour is fixed, so whether a given minute is daytime is known
  when the schedule is written.
- **Collision with a book find:** v1 drops a special event on a tick where a book is found.
  In v2 a scheduled event that lands on a book-found tick is **deferred one tick**, so every
  runner still receives every scheduled event.
- **Hallucinations** keep their own channel (`Observation.hallucination`), independent of
  events, as in v1. The schedule should respect the v1 sleep-debt onset
  (`HALLUCINATION_ONSET_MIN`) so they still read as fatigue, not noise. `severity()` stays,
  because memory jumbling uses it.
- **Runners that have ended** (finished / DNF) receive nothing further.

### What gets deleted

Following "no backwards support": `step_weather` + `TRANSITION_WEIGHTS`, the `*_CHANCE_PER_TICK`
constants, `hallucinations.roll`, the `rng` parameter through `frozen_head_state_park`,
`Checkpoint.rng_state`, `db.serialize_rng_state` / `deserialize_rng_state` / `rng_from_state`.

### Tests

- Same config, **different** scripted decisions → identical weather/event/hallucination
  sequence. This is the property the whole study rests on.
- Same config, same scripted decisions → identical run, tick for tick.
- GPS noise at tick _t_ depends only on `(seed, elapsed_min)` and the runner's state then.
- A scheduled event landing on a book-found tick is delivered next tick.
- `test_resume.py` reference-vs-resume still matches, now without rng state in the checkpoint.
- Existing park / course / hallucination tests rewritten for the scheduled versions.

### ADRs

- New: "Fixed race conditions via RaceConfig". Supersedes ADR-0003's single injected rng for
  the sim, and amends ADR-0016 (events) and ADR-0017 (hallucinations) from rolled to scheduled.

---

## Phase 2: OpenRouter migration

Replace the `anthropic` SDK with the OpenAI SDK pointed at OpenRouter, for every model,
Haiku included (`anthropic/claude-haiku-4.5`).

- **Client:** `from langfuse.openai import AsyncOpenAI` with
  `base_url="https://openrouter.ai/api/v1"` and `api_key=OPENROUTER_API_KEY`. The Langfuse
  wrapper traces calls itself, so `opentelemetry-instrumentation-anthropic` and ADR-0006's
  import-order dance go away. ADR-0006 is superseded.
- **Structured output:** `response_format={"type": "json_schema", "json_schema": {"name":
  "decision", "strict": true, "schema": ...}}` plus `provider={"require_parameters": true}` so
  OpenRouter only routes to endpoints that honour it. Support is per endpoint, not per model.
  Haiku's OpenRouter page lists `response_format` but not `structured_outputs` explicitly, so
  the first slice confirms it with a live call. If a model can't do strict schemas, Pydantic
  validation in `decide()` still catches bad output ("mumbles incoherently").
- **Temperature 1:** sent explicitly. Caveat to verify: `require_parameters` applies to
  **every** parameter sent, so a model that doesn't accept `temperature` (some reasoning
  models) would find no endpoint. Fix: per-model flag in the roster saying whether to send it.
- **Prompt caching:** keep the `cache_control` block on the summary for Anthropic models
  (OpenRouter passes it through). DeepSeek/OpenAI-style providers cache prefixes
  automatically. Others may not cache at all, and that cost difference is part of the
  comparison. OpenRouter's sticky routing (pass `session_id`) keeps a runner on the same
  provider so its cache stays warm.
- **Cost tracking:** `extra_body={"usage": {"include": True}}` so Langfuse records real
  OpenRouter cost, not an estimate.
- **Tracing attributes:** `session_id=runner_id`, plus tags for model, race config name, and
  study run.
- **Message format:** `build_prompt` already uses the OpenAI-compatible `role/content` shape.
  Only the `system` prompt moves from a top-level parameter into the first message.
- **Bounds on Decision:** add `Field(ge=1, le=10)` on `effort` and bounds on `rest_min` /
  `bearing_deg`. Nothing clamps them today, and `physiology.py` will take `effort: 40` at face
  value. Haiku stayed in range, but other models may not.
- **Reasoning models:** turn thinking off or strip it, or they fail to parse and run slowly.
- **Config:** `ANTHROPIC_API_KEY` → `OPENROUTER_API_KEY` in `.env`, `.env.example`, Fly
  secrets. Update CLAUDE.md's Stack section.
- **Cost:** OpenRouter bills at the providers' prices; check its current fee on credit
  purchases. Haiku stays roughly what it costs today.

---

## Phase 3: Multi-runner sim

- **Runner identity:** today `runner_id = persona.name`, so N models running "Hank" would
  overwrite each other's checkpoints, turns, monologue feed and WS entry. New
  `runner_id = f"{persona}-{model_slug}"`; `RunnerState` / `Checkpoint` gain `model` and a
  display label; `/monologues/{persona_name}` becomes `/monologues/{runner_id}`; a distinct bib
  per runner.
- **Roster file** `agents/roster.yaml`: list of `{model, label, send_temperature}`, all
  pointing at the one persona file, so the system prompt is identical by construction.
- **Shared world:** step weather/clock once per tick, then each runner against it (the
  `world.step(); for r in runners: r.step(world)` shape CLAUDE.md already describes). Phase 1
  makes this simple, since the world no longer shares an rng with runners.
- **Checkpoints:** a race-level checkpoint (config name/hash, elapsed) plus one per runner.
- **Race end per runner:** finished / DNF runners stop ticking; the race ends when all are
  terminal or the cutoff hits. `_finalize_race_end`, `_maybe_fallback_checkpoint` and
  `_broadcast_already_ended_race` loop over runners.
- **Broadcast bug to fix:** `think()` broadcasts a `RaceState` holding only its own runner, and
  the frontend reducer replaces `runners` wholesale. With N runners, every brain call would
  wipe the others from the UI. Broadcast merged state (or merge in the reducer).
- **Concurrency:** per-runner (or per-provider) semaphores instead of one shared
  `Semaphore(5)`, so one slow provider can't starve the others.
- **Monitoring:** `db.get_health_summary` / `scripts/monitor_race.py` report per runner.
  Otherwise one broken model looks like a broken race.
- **Compaction cost:** `_compact_and_checkpoint` reads and parses a runner's full history on
  every decision (quadratic over a 60h race). Fetch only turns past `summary_folded_count`.
  Matters more with N runners on a 512MB shared-CPU Fly machine.

### Open decision: model latency

"The sim never waits for the LLM" means a slower model makes fewer decisions per sim-minute.
At 1x (30s ticks) this barely matters; at `speed=20` (1.5s ticks) a 4s model is always acting
on stale decisions while a fast one isn't. That makes latency a second variable. Options: accept
it (arguably part of the model's character), run study races at 1x only, or add a lockstep
study mode. Related: a call is spawned every tick even if the previous one hasn't returned, and
nothing stops an older call landing after a newer one and overwriting its decision. Either skip
spawning while a call is in flight, or tag decisions with their tick and drop stale ones. Both
change ADR-0015.

---

## Phase 4: Frontend grid

- **Tiles:** `App.tsx` and `RaceViewer` use `Object.values(runners)[0]`. Extract a
  `RunnerTile` (watch face + monologue feed + status/outcome) and map it over runners in a CSS
  grid. The store is already keyed by name; switch the key to `runner_id`.
- **WebGL budget:** each tile with its own MapLibre map **and** react-three-fiber scene is two
  WebGL contexts. Browsers allow roughly 16, and 6–8 tiles of 3D is heavy. Proposed: light
  tiles, plus **one shared map with a colour-coded dot (and ghost dot) per model**, which is also
  the clearest view for comparing them, and click-to-expand for a tile's 3D scene.
- Regenerate types (`openapi-typescript`), add a multi-runner mock JSON, per-tile outcome/Taps.

---

## Phase 5: Study runs

- **Fixed sim doesn't mean repeatable runs.** At temperature 1 (and even at 0 on most
  providers) one different decision moves the runner, which changes terrain, which changes
  everything after. So each model needs **several runs per race config** (e.g. 3–5), and
  results are compared as distributions, not single outcomes.
- **Metrics to pull from SQLite + Langfuse:** outcome (finish / DNF type / loops / books),
  sim-time to each book and loop, time spent off-trail, brain-call failure rate (invalid JSON vs
  API error), decision latency, tokens and cost per decision, how often it repeats the same
  decision (the "stuck" behaviour the persona prompt warns about).
- **Token volume per runner per full race** (estimate from the prompt shape: ~1.5k-token
  system prompt + 20-turn window at ~350 tokens/turn + summary): roughly 8–10k input tokens per
  call × 7,200 calls ≈ **60–70M input tokens per model per 60h race**. Real numbers are in the
  v1 Langfuse traces. `SLIDING_WINDOW_N` and call cadence are the cost levers.
- Free tiers cap out well below the ~2,900 calls/day one runner makes at 1x. Fine for short
  sped-up slices only.
- Model shortlist: **TBD**.

## CLAUDE.md changes this implies

Stack (Anthropic → OpenRouter), Data contract (`Decision` bounds, `model` on `RunnerState`),
Core rule (semaphore per runner, in-flight policy), Build order (step 4 becomes multi-model,
same persona), Live Testing (`POST /run?race=…`). Updated phase by phase as each lands, not
up front.
