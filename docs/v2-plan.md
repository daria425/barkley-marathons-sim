# v2: Controlled multi-model study

v1 ran one model (Haiku) through one race whose conditions were deliberately random. v2 turns
that into a **study**: several models run the same persona, the same system prompt and the same
race conditions, so **the model is the only variable that changes**. The LLM's own sampling
variance (temperature 1) is kept on purpose: it's the interesting part.

Status: **Phase 1 done, Phase 2 next.** Each phase still gets its own plan check-in before code
(CLAUDE.md's plan-per-phase rule). `[x]` = done and verified; `[ ]` = still to do.

## Decisions so far

- [x] **Everything in the sim is fixed, not random.** A `RaceConfig` pins the seed, the start
  hour and the weather. No backwards compatibility with v1's random mode: reverting to v1 means
  `git checkout`, not a runtime flag. (ADR-0024)
- [x] **Events and hallucinations stay, but fire at fixed points** instead of being rolled per
  tick. (ADR-0024)
- **Full migration to OpenRouter.** No direct Anthropic calls. Claude (Haiku) runs through
  OpenRouter like every other model.
- **Temperature 1** wherever the provider supports it, via a per-model `send_temperature` flag
  (decided 2026-11-01).
- The first v1 Haiku run does **not** need to be reproduced.
- Frontend shows each model's run as a tile in a grid.
- **Navigation stays as it is for the first study run** (decided 2026-11-01). Runners spinning
  in the brush is the interesting part; don't tune the course or the prompt to stop it yet.
- **Prompt caching isn't a priority** (decided 2026-11-01). It's a no-op today: Langfuse showed
  0 cached tokens on all 120 calls of the 2026-11-01 run, because the cached prefix (~1.5k
  tokens) is below Haiku 4.5's minimum cacheable length. Revisit when cost matters.
- **Model latency: deferred** (decided 2026-11-01). See Phase 3's open decision.

## Phase order

| Phase | What | Status |
|---|---|---|
| 1 | Deterministic race (`RaceConfig`) | **done** |
| 2 | OpenRouter migration | next |
| 3 | Multi-runner sim (roster, shared world) | not started |
| 4 | Frontend grid | not started |
| 5 | Study runs | not started |

Each phase gets a thin, sped-up slice first (ADR-0007) and its own plan check-in.

---

## Phase 1: Deterministic race (done)

Background and rationale are in ADR-0024. In short: v1's randomness all came from one unseeded
`random.Random()`, and seeding it isn't enough, because event rolls only drew numbers on certain
terrain or at night. So the number of draws depended on the runner's path, and two runs with the
same seed drifted apart, weather included. v2 drops the shared rng: weather, events and
hallucinations are schedules, and GPS noise draws from `Random(f"{seed}:gps:{elapsed_min}")`,
fresh each tick.

### Randomness replaced

| v1 source | v2 | |
|---|---|---|
| Start hour, random 0–12h | `RaceConfig.start_hour` (06:00) | [x] |
| Starting weather + Markov changes | `RaceConfig.weather_cycle`, clear 2h → fog 2h → rain 2h | [x] |
| Temperature jitter ±1°C | removed: diurnal curve + weather offset only | [x] |
| Fog jitter ±5% | removed: weather + night only | [x] |
| GPS noise | seeded per tick from `(seed, elapsed_min)` (`race_config.gps_rng`) | [x] |
| Special events | `RaceConfig.events` schedule (38 in study-01) | [x] |
| Hallucinations | `RaceConfig.hallucinations` schedule (16 in study-01, from 40h) | [x] |
| Memory jumbling | unchanged (sha256 of the text); onset moved to real 40h/55h | [x] |
| LLM sampling | **kept**, temperature 1 | Phase 2 |

### Checklist

- [x] `RaceConfig` model + YAML loader + pure lookups (`sim/race_config.py`)
- [x] `server/races/study-01.yaml`: seed, 06:00 start, weather cycle, events placed to fit
  weather and darkness, hallucinations from 40h
- [x] `POST /run?race=<name>` required; bad or unknown names rejected
- [x] Events fire at their minute wherever the runner is (terrain gating dropped)
- [x] An event landing on a `found_book` tick waits in `pending_events`, one per tick
- [x] Runners that have ended receive nothing further
- [x] Checkpoint stores `race_config_name`, `race_config_hash`, `pending_events`; resuming
  against an edited config raises `RaceConfigMismatch` (not retried by the supervisor)
- [ ] Config **hash** on every Langfuse trace. Only `race:<name>` is tagged today. Moved to
  Phase 2's tracing item, since Phase 2 replaces the tracing path anyway.
- [x] Deleted: `step_weather` + `TRANSITION_WEIGHTS`, `*_CHANCE_PER_TICK`,
  `hallucinations.roll`, the `rng` parameter through the park, `Checkpoint.rng_state`,
  `db.serialize_rng_state` / `deserialize_rng_state` / `rng_from_state`
- [x] Tests:
  - [x] same config, different scripted decisions → identical conditions
    (`test_conditions_are_identical_whatever_the_runner_decides`)
  - [x] same config, same decisions → identical run (`test_same_config_and_decisions_reproduce_the_whole_run`)
  - [x] GPS noise depends only on seed + minute (`test_gps_rng_is_the_same_stream_…`, `test_gps_noise_depends_on_seed`)
  - [x] event on a book-found tick delivered next tick (`test_scheduled_event_waits_out_a_found_book_tick`)
  - [x] reference-vs-resume still bit-exact, without rng state (`test_resume_continues_bit_exactly_…`)
  - [x] park / course / hallucination tests rewritten for the scheduled versions
- [x] ADR-0024 written; amends ADR-0003, ADR-0016, ADR-0017
- [x] Live slice: `study-01`, 60 sim-min at speed 20 (2026-11-01): 120 calls, 0 failures, ended
  `dnf_cutoff`, minute-40 wildlife event fired on time

### Fixes that came out of the Phase 1 slices

- [x] Over-eating: the model read "last ate 0 min ago" as "never ate" and ate on 79/120 turns.
  Fixed with "You just ate." wording, a drink counter, realistic glycogen/hydration drain and
  dehydration effects (ADR-0025). Next run: 3 eats and 3 drinks in 120 turns.
- [x] Banker's rounding on the clock: `round()` sends .5 to the nearest even number, so with 30s
  ticks `Observation.elapsed_min` and `clock_time` showed even minutes for 3 ticks and odd
  minutes for 1 (6:26, 6:26, 6:26, 6:27, 6:28). Both now floor (`sim_utils.whole_minutes`).

---

## Phase 2: OpenRouter migration (next)

Replace the `anthropic` SDK with the OpenAI SDK pointed at OpenRouter, for every model,
Haiku included (`anthropic/claude-haiku-4.5`).

**First slice (decided 2026-11-01): Haiku only, through OpenRouter.** Prove the client,
structured output, tracing and temperature handling on the one model we already have a
baseline for, before adding a roster.

- [ ] **Client:** `from langfuse.openai import AsyncOpenAI` with
  `base_url="https://openrouter.ai/api/v1"` and `api_key=OPENROUTER_API_KEY`. The Langfuse
  wrapper traces calls itself, so `opentelemetry-instrumentation-anthropic` and ADR-0006's
  import-order dance go away. ADR-0006 is superseded.
- [ ] **Structured output:** `response_format={"type": "json_schema", "json_schema": {"name":
  "decision", "strict": true, "schema": ...}}` plus `provider={"require_parameters": true}` so
  OpenRouter only routes to endpoints that honour it. Support is per endpoint, not per model.
  Haiku's OpenRouter page lists `response_format` but not `structured_outputs` explicitly, so
  the first slice confirms it with a live call. If a model can't do strict schemas, Pydantic
  validation in `decide()` still catches bad output ("mumbles incoherently").
- [ ] **Temperature 1, per-model `send_temperature` flag** _(decided)_. `require_parameters`
  applies to **every** parameter sent, so a model that rejects `temperature` (some reasoning
  models) would find no endpoint. Models with the flag off get the provider default.
- [ ] **Tracing attributes:** `session_id=runner_id`, plus tags/metadata for model, race config
  name **and hash** (carried over from Phase 1), and study run.
- [ ] **Cost tracking:** `extra_body={"usage": {"include": True}}` so Langfuse records real
  OpenRouter cost, not an estimate.
- [ ] **Message format:** `build_prompt` already uses the OpenAI-compatible `role/content`
  shape. Only the `system` prompt moves from a top-level parameter into the first message.
- [ ] **Bounds on Decision:** `Field(ge=1, le=10)` on `effort`, plus bounds on `rest_min` and
  `bearing_deg`. Nothing clamps them today, and `physiology.py` takes `effort: 40` at face
  value. Haiku stayed in range, but other models may not.
- [ ] **Reasoning models:** turn thinking off or strip it, or they fail to parse and run slowly.
  (Not needed for the Haiku slice.)
- [ ] **Config:** `ANTHROPIC_API_KEY` → `OPENROUTER_API_KEY` in `.env`, `.env.example`, Fly
  secrets. Update CLAUDE.md's Stack section.
- [ ] **ADR:** "OpenRouter for every model", superseding ADR-0006.
- [ ] **Live slice:** Haiku via OpenRouter on `study-01`, compared against the 2026-11-01
  direct-Anthropic run (failures, latency, tokens, cost).
- **Prompt caching:** deferred (see Decisions). If revisited: `cache_control` on Anthropic
  models passes through OpenRouter; DeepSeek/OpenAI-style providers cache prefixes
  automatically; sticky routing via `session_id` keeps a runner's cache warm.
- **Cost:** OpenRouter bills at the providers' prices; check its current fee on credit
  purchases. Baseline from the 2026-11-01 run: ~8k input tokens/call, **$1.08 per sim-hour**
  for Haiku with no caching, so ~$65 per model per full 60h race.

---

## Phase 3: Multi-runner sim

- [ ] **Runner identity:** today `runner_id = persona.name`, so N models running "Hank" would
  overwrite each other's checkpoints, turns, monologue feed and WS entry. New
  `runner_id = f"{persona}-{model_slug}"`; `RunnerState` / `Checkpoint` gain `model` and a
  display label; `/monologues/{persona_name}` becomes `/monologues/{runner_id}`; a distinct bib
  per runner.
- [ ] **Roster file** `agents/roster.yaml`: list of `{model, label, send_temperature}`, all
  pointing at the one persona file, so the system prompt is identical by construction.
- [ ] **Shared world:** step weather/clock once per tick, then each runner against it (the
  `world.step(); for r in runners: r.step(world)` shape CLAUDE.md already describes). Phase 1
  makes this simple, since the world no longer shares an rng with runners.
- [ ] **Checkpoints:** a race-level checkpoint (config name/hash, elapsed) plus one per runner.
- [ ] **Race end per runner:** finished / DNF runners stop ticking; the race ends when all are
  terminal or the cutoff hits. `_finalize_race_end`, `_maybe_fallback_checkpoint` and
  `_broadcast_already_ended_race` loop over runners.
- [ ] **Broadcast bug:** `think()` broadcasts a `RaceState` holding only its own runner, and
  the frontend reducer replaces `runners` wholesale. With N runners, every brain call would
  wipe the others from the UI. Broadcast merged state (or merge in the reducer).
- [ ] **Concurrency:** per-runner (or per-provider) semaphores instead of one shared
  `Semaphore(5)`, so one slow provider can't starve the others.
- [ ] **Monitoring:** `db.get_health_summary` / `scripts/monitor_race.py` report per runner.
  Otherwise one broken model looks like a broken race.
- [ ] **Compaction cost:** `_compact_and_checkpoint` reads and parses a runner's full history on
  every decision (quadratic over a 60h race). Fetch only turns past `summary_folded_count`.
  Matters more with N runners on a 512MB shared-CPU Fly machine.

### Open decision: model latency (deferred)

"The sim never waits for the LLM" means a slower model makes fewer decisions per sim-minute.
At 1x (30s ticks) this barely matters; at `speed=20` (1.5s ticks) a 4s model is always acting
on stale decisions while a fast one isn't. That makes latency a second variable. The
2026-11-01 run already shows it: Haiku's median latency was 3.1s (p90 3.9s) against 1.5s ticks,
so about 2 calls were in flight at any moment. Options: accept it (arguably part of the model's
character), run study races at 1x only, or add a lockstep study mode. Related: a call is
spawned every tick even if the previous one hasn't returned, and nothing stops an older call
landing after a newer one and overwriting its decision. Either skip spawning while a call is
in flight, or tag decisions with their tick and drop stale ones. Both change ADR-0015.

- [ ] Decide before Phase 5's study runs.

---

## Phase 4: Frontend grid

- [ ] **Tiles:** `App.tsx` and `RaceViewer` use `Object.values(runners)[0]`. Extract a
  `RunnerTile` (watch face + monologue feed + status/outcome) and map it over runners in a CSS
  grid. The store is already keyed by name; switch the key to `runner_id`.
- [ ] **WebGL budget:** each tile with its own MapLibre map **and** react-three-fiber scene is
  two WebGL contexts. Browsers allow roughly 16, and 6–8 tiles of 3D is heavy. Proposed: light
  tiles, plus **one shared map with a colour-coded dot (and ghost dot) per model**, which is
  also the clearest view for comparing them, and click-to-expand for a tile's 3D scene.
- [ ] Regenerate types (`openapi-typescript`), add a multi-runner mock JSON, per-tile
  outcome/Taps.

---

## Phase 5: Study runs

- **Fixed sim doesn't mean repeatable runs.** At temperature 1 (and even at 0 on most
  providers) one different decision moves the runner, which changes terrain, which changes
  everything after. So each model needs **several runs per race config** (e.g. 3–5), and
  results are compared as distributions, not single outcomes.
- [ ] Model shortlist: **TBD**.
- [ ] **Metrics to pull from SQLite + Langfuse:** outcome (finish / DNF type / loops / books),
  sim-time to each book and loop, time spent off-trail, brain-call failure rate (invalid JSON vs
  API error), decision latency, tokens and cost per decision, how often it repeats the same
  decision (the "stuck" behaviour the persona prompt warns about), how often it changes bearing
  (54 of 119 turns in the 2026-11-01 Haiku run).
- [ ] Runs: several per model per race config.
- **Token volume:** measured ~8k input tokens per call in the 2026-11-01 run, so × 7,200 calls
  ≈ **57M input tokens per model per 60h race**. `SLIDING_WINDOW_N` and call cadence are the
  cost levers.
- Free tiers cap out well below the ~2,900 calls/day one runner makes at 1x. Fine for short
  sped-up slices only.

## CLAUDE.md changes this implies

Updated phase by phase as each lands, not up front.

- [x] Phase 1: v2 section, `RaceConfig` in Layout, Live Testing uses `POST /run?race=…`,
  scheduled events/hallucinations in Physiology
- [ ] Phase 2: Stack (Anthropic → OpenRouter), Data contract (`Decision` bounds)
- [ ] Phase 3: Data contract (`model` on `RunnerState`), Core rule (semaphore per runner,
  in-flight policy), Build order (step 4 becomes multi-model, same persona)
