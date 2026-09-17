# Barkley Sim: AI agents run an ultra

A comedic simulation of LLM agents running a Barkley Marathons–style ultra. Code simulates the body and the world. The LLM is only the runner's _brain_, making decisions every so often. The fun comes from bad navigation, bonking, quitting and navigating a tough environment.

## How we work together

This is a collaboration, not a hand-the-keys-over build. Specifically:

- **Plan mode per phase.** Before starting each phase in the Build order below, propose a short approach (what files, what interfaces, what's deliberately deferred) and wait for a go-ahead. Small decisions _within_ an agreed phase don't need a check-in.
- **Don't silently re-scope.** If a phase turns out to need something not in this file (a new dependency, a schema change, a reordering), surface it and get agreement before running with it — don't just decide and proceed.
- **Testing bar is decided per-phase**, not fixed upfront. `physiology.py` is the one hard requirement: pure functions, fully unit-tested (property-based invariants first — e.g. HR rises with effort+heat, glycogen never negative, bonking collapses pace — then a reference-data validation pass against rough real ultrarunning data once the shape is right).
- This doc reflects real decisions made in a planning session, not aspirations. If something here turns out to be wrong once we're building, fix the doc, don't quietly diverge from it.

## Race rules (Barkley-inspired)

- 5 loops of ~20 miles each, 60-hour cutoff
- Hidden "books" along each loop. Runner must tear out their bib-number page as proof
- No GPS for runners: they navigate with a compass and a noisy position estimate

## Scope: v1 vs later

**v1 ("one runner thinks and runs")**: single runner, single persona, LLM-driven decisions, full physiology + weather/environment + course/books + noisy believed-position navigation. Real concurrency pattern (semaphore + fire-and-forget tasks + last-decision-wins) built now, not deferred, since it doesn't get simpler by waiting. SQLite logging + Langfuse tracing wired in from v1. **No frontend in v1** — verify behavior by connecting to the WebSocket directly (e.g. `websocat`/a small script) and watching state + brain calls stream live, plus SQLite queries after the fact.

- **No race-end concept yet.** `WorldState`/`RunnerState` don't need to model finishing all 5 loops or hitting the 60h cutoff for v1 — for now we just want to watch it run and see what happens. Finish-line/cutoff handling gets designed later, once there's something worth finishing.
- **Speed multiplier is a dev convenience, not the target mode.** The eventual "real" way to run this is at 1x realtime for the full ~60 hours, so runner behavior and pacing stay realistic. 60x/600x speed is for iterating during development, not the intended experience.
- **v1's API surface:** a start endpoint (REST) to kick off a run, and a **WebSocket from v1** streaming live `WorldState`/`RunnerState` updates plus brain-call/monologue events — this is what "no frontend yet" is verified against, and it's the same contract the frontend plugs into later. No separate polling/REST-status endpoint needed for now.

**Right after v1**: SQLite-backed checkpoint/resume becomes load-bearing (not just nice-to-have logging) — see "Memory and persistence" below.

**Later phase**: multiple competing personas (5–10 runners).

**Stretch / documented but not built yet**: the full frontend (MapLibre map, ghost dots, watch cards, monologue feed, speed controls, Taps-on-quit) — see Frontend section, kept here so the shape is agreed even though it's not in scope yet.

## Stack

- **Backend:** Python, FastAPI + uvicorn, native WebSockets, asyncio sim loop
- **LLM:** `anthropic` AsyncAnthropic client, model `claude-haiku-4-5-20251001`, called through a thin `complete()` wrapper (see Brain below) — cheap insurance against ever wanting to swap providers, without adding an actual gateway
- **Observability:** Langfuse, tracing Anthropic calls from v1 onward
- **Schemas:** Pydantic v2 (source of truth)
- **Storage:** SQLite via aiosqlite or SQLModel (source of truth for runner history, checkpoint/resume, LLM memory — see below)
- **Geo:** gpxpy (course), haversine (distances)
- **Project mgmt:** uv
- **Frontend (later phase):** React + Vite + TypeScript + MapLibre
- **Type sync (later phase):** generate TS types from FastAPI's OpenAPI schema with `openapi-typescript`. Never hand-write duplicate types. Regenerate whenever `models.py` changes.

## Deployment target

Kept in mind for config decisions now, not built yet:

- **Backend** (FastAPI + WebSocket + asyncio loop): Fly.io.
- **Frontend** (later phase): Vercel.
- Split targets mean CORS and the WS URL must be env-driven from the start — never hardcode `localhost`.
- Secrets via a local `.env` (gitignored), loaded with `python-dotenv`. Same var names get set as platform secrets on Fly.io when we actually deploy.

## Layout

```
/server
  main.py            FastAPI app, WS endpoint, start/stop run
  models.py          Pydantic: Observation, Decision, RunnerState, WorldState
  sim/loop.py        async tick loop, speed multiplier
  sim/physiology.py  PURE functions, no async, no API calls
  sim/course.py      gpxpy loop, books, off-course terrain
  sim/world.py       weather, day/night, fog
  agents/brain.py    prompt build, thin complete() wrapper around AsyncAnthropic, parse into Decision
  agents/personas.py loads persona YAML/JSON files
  agents/personas/   persona data files (name, traits, system prompt template)
  agents/memory.py   sliding-window history + autocompact summary for prompting
  db.py              SQLite schema + checkpoint/resume
/web                 (later phase)
  src/components/    Map, WatchFace, MonologueFeed, Controls
  src/types/         generated from OpenAPI
```

## Core rule: the sim never waits for the LLM

- The loop ticks independently (1 tick = 1 sim-minute, with a speed multiplier of 1x/60x/600x).
- Each runner keeps executing its **last decision** until a new one arrives.
- Brain calls fire async via `asyncio.create_task`, either every N sim-minutes or on trigger events: fall, lost, bonk, book found, loop complete, quit consideration. **N is not decided yet** — pick it during Phase 1 planning, not before.
- Cap concurrency with `asyncio.Semaphore(5)` — built now even though v1 has one runner, so multi-persona later is just raising N, not re-architecting.
- If the LLM call fails or returns invalid JSON, catch the error, **keep the old decision**, and log a funny line ("runner mumbles incoherently"). No retries — try again on the next scheduled thought.

```python
async def think(runner):
    async with sem:
        obs = runner.observe(world)
        decision = await brain.decide(runner.persona, obs)
        runner.decision = decision  # applied next tick

async def loop():
    while running:
        world.step()
        for r in runners:
            r.step(world)
            if r.needs_thought():
                asyncio.create_task(think(r))
        await ws.broadcast(state_diff())
        await asyncio.sleep(1 / speed)
```

## Data contract

```python
class Observation(BaseModel):
    elapsed_min: int
    hr: int
    pace_min_per_km: float
    cadence: int
    feel: str              # "legs heavy", "bonking", etc.
    last_ate_min_ago: int
    bearing_deg: float
    gps_guess: tuple[float, float]  # NOISY believed position
    terrain: str           # "thick briars", "creek crossing"
    weather: str
    books_found: int
    loop: int
    hallucination: str | None

class Decision(BaseModel):
    effort: int            # 1-10
    eat: bool
    drink: bool
    bearing_deg: float
    rest_min: int
    quit: bool
    monologue: str
```

## Physiology (keep simple, tune before adding LLM)

- HR = f(effort, grade, heat, cardiac drift over elapsed time)
- Glycogen drains with effort and refills when eating. At zero, pace collapses and `feel` = "bonking"
- Hydration drains faster with heat
- Core temp rises with effort + heat
- Sleep debt past ~40h adds a random chance of hallucination events, which get injected into the observation

## Comedy engine: true vs believed position

- Every runner has `true_pos` and `believed_pos` — this is part of the v1 single-runner core loop, not gated on multi-persona.
- The agent only sees `believed_pos` (noisy). Noise increases with fog, night, and fatigue.
- Frontend (later phase) draws the real dot, a ghost dot at believed position, and a line between them.

## Memory and persistence

The LLM needs continuity — it can't reason about "wtf happened before" without it — and the sim needs to survive an API failure or crash without losing a runner's race. One mechanism serves both:

- **SQLite is the source of truth.** Every Observation + Decision pair is logged, and a checkpoint is written **on every brain decision** (not on a timer) — this is when there's genuinely new state worth not losing.
- **Prompting uses a sliding window + autocompact.** Each brain call gets the last **N=10** full Observation/Decision objects verbatim, plus a running summary of everything older. When history exceeds N, an **LLM call** (not code) compresses the aged-out objects into the summary — similar to chatbot context autocompaction. This costs an extra call per compaction but reads as a coherent narrative rather than a stats dump.
- **Resume-from-checkpoint is handled ourselves** — no LangGraph or external state-machine library. On restart, load the latest checkpoint + summary + last-N window from SQLite and continue.
- This is built as the phase **right after v1** — v1 itself can run in-memory to keep the first milestone small, but the schema and access patterns should be designed with this follow-up in mind so it's not a rewrite.

## Personas

- Personas are **data files** (YAML/JSON) under `agents/personas/`, not Python constants — name, traits, and system prompt template live outside code so tuning a persona doesn't require touching Python. `agents/personas.py` just loads and validates them (Pydantic).
- v1 ships with exactly one persona. Examples for the later multi-persona phase:
  - Cocky road marathoner who's never been off pavement
  - Grizzled Barkley veteran, laconic, trusts the compass
  - "Just here for the vibes" guy
  - Over-prepared data nerd narrating their own splits
- Tell each to write short, in-character `monologue` lines.

## Frontend (later phase — documented now, not built)

- MapLibre map: runner dots, ghost dots, connecting lines, book markers
- Garmin-style watch card per runner (HR, pace, elapsed, glycogen, hydration)
- Scrolling monologue feed
- Speed controls (1x / 60x / 600x), start/pause/reset
- Quit = bugle icon (Barkley plays Taps)

## Build order

1. **v1 — one runner, full loop, no frontend.** Weather/environment sim → physiology → course/books/noisy-position navigation → wire in the one LLM persona (direct AsyncAnthropic via `complete()`, Langfuse traced). Verify via logs/SQLite/API, not a UI. Physiology gets property-based unit tests before the LLM is plugged in; tune against reference data once behavior looks right.
2. **Persistence + resume.** SQLite logging, checkpoint-per-decision, sliding-window + LLM-autocompacted memory, resume-on-restart.
3. **Multi-persona.** 5–10 personas racing concurrently, using the concurrency pattern already built in v1.
4. **Frontend.** Map, watch cards, monologue feed, controls — the experience described above, built against the by-then-stable API/WS contract.
5. **Let it rip.** Polish, more personas, more comedy.

Each numbered phase gets its own plan-mode check-in before code starts, per "How we work together" above.

## Linting & code style

- **Tool:** [ruff](https://docs.astral.sh/ruff/) for both linting and formatting (`server/pyproject.toml`) — one tool, no separate black/isort/flake8.
- **Rules enabled:** pyflakes (`F`), pycodestyle (`E`/`W`), import sorting (`I`), pyupgrade (`UP`), bugbear (`B`), mccabe complexity (`C90`).
- **Max complexity: 10** (`mccabe.max-complexity`). If a function trips this, that's a signal to split it, not to raise the limit — raise it only with a specific reason, not to make a violation go away.
- **Line length: 100.** Double quotes.
- **Enforced via pre-commit hook** (`.pre-commit-config.yaml`, scoped to `server/`): `ruff check --fix` then `ruff format` run automatically on every commit. Installed once via `uv tool install pre-commit && pre-commit install`; after that it's automatic — don't reach for `--no-verify` to skip it.
- Run manually any time: `cd server && uv run ruff check . && uv run ruff format .`
- The `/web` frontend (later phase) gets its own eslint + prettier config when that phase starts — not set up yet since there's no frontend code.
- No type checker yet (mypy) — revisit if untyped bugs actually start costing time.

## Conventions

- `physiology.py` stays pure and fully unit-tested (pytest).
- API key via `ANTHROPIC_API_KEY` env var (and Langfuse keys), loaded via `.env`, never committed.
- Log every Decision + Observation to SQLite — this is load-bearing for LLM memory and crash recovery, not just a replay nice-to-have.
- For key decision moments use architecture-decision-records skill in order to log a change properly, in a new session check if a docs/adr directory exists already and read its files to get an overview of the project state
