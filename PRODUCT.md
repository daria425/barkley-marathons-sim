# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

People curious about watching an LLM agent struggle at an embodied, physically demanding task — not necessarily ultrarunners or Barkley followers. The frontend's job is to make an AI agent's live reasoning and navigation legible and watchable to a general AI-curious audience, not to assume trail-running domain knowledge.

## Product Purpose

Barkley Sim simulates an LLM agent ("the brain") attempting a Barkley Marathons–style ultra: 5 loops of ~20 miles, 60-hour cutoff, hidden "books" to find as proof of passage, no GPS (compass + noisy position estimate only). Code simulates the body (HR, glycogen, hydration, core temp, sleep debt) and the world (weather, fog, day/night, terrain); the LLM only makes periodic decisions (effort, eat, drink, bearing, rest, quit) based on a degraded observation of its own state. Success for the project is a clear, progressive, live view into the runner's thoughts and navigation as it unfolds — the comedy (bad navigation, bonking, hallucinations, quitting) is meant to emerge from a real simulation, not be authored directly, but the primary product bar is legibility of that unfolding decision process in real time, over the frontend.

## Positioning

The distinguishing mechanism is the true-vs-believed-position split: the agent reasons and acts on a noisy, fog/fatigue-degraded belief about its own location, never the ground truth, and the frontend is expected to show both (real dot, ghost dot, the gap between them) so the disconnect between what the runner believes and what's actually happening is visible, not just implied by narration.

## Operating Context

- Backend: FastAPI + asyncio sim loop, WebSocket streams live `RaceState`/`RunnerState` plus brain-call/monologue events; a REST endpoint starts a run.
- Frontend (`/web`, in progress): React + Vite + TypeScript. Components scaffolded so far: `Map`, `WatchFace`, `MonologueFeed`, `Controls`, backed by a Redux store (`raceSlice`) and a `useRaceSocket` WS hook consuming generated API types.
- Intended frontend experience (per CLAUDE.md): MapLibre map with real/ghost runner dots and a connecting line, book markers; a Garmin-style watch card per runner (HR, pace, elapsed, glycogen, hydration); a scrolling monologue feed of the LLM's in-character reasoning; speed controls (1x/60x/600x) and start/pause/reset; a quit action styled as the race's bugle/Taps convention.
- v1 scope is a single runner/persona at real or sped-up time; multi-persona (5–10 concurrent runners) is a later phase reusing the same concurrency pattern.
- Deployment target: backend on Fly.io, frontend on Vercel — kept in mind for env-driven config (CORS, WS URL), not yet deployed.

## Capabilities and Constraints

- The frontend must work against the WebSocket contract already streaming `RaceState`/`RunnerState` + brain-call/monologue events (this is the live data source, not mocked data).
- No finish-line/cutoff UI concept yet — the sim doesn't model completing all 5 loops or hitting the 60h cutoff yet, so the frontend shouldn't presuppose an end state.
- Multi-runner display (ghost dots per persona, multiple watch cards) is a near-future need once the multi-persona phase lands; current UI targets a single runner but shouldn't be architected to make multi-runner a rewrite.
- Speed multiplier (1x/60x/600x) is a real, user-facing control, not just a dev toggle — the frontend needs to represent sim time clearly at all three speeds.

## Brand Commitments

Project name is locked: **Barkley Sim**. No other voice, palette, typography, or visual asset commitments exist yet.

## Evidence on Hand

- `docs/adr/` — architecture decision records documenting real build decisions (memory/compaction, resume, WS wiring, navigation scoping, etc.).
- `server/files/Barkley_Challenge_Loop_FKT.gpx` — real course GPX data driving `sim/course.py`.
- No testimonials, case studies, press, or user research exist; none should be fabricated.

## Product Principles

- Legibility of live agent reasoning over polish — the frontend's core job is making the runner's unfolding thoughts and navigation clear and watchable, not decorative.
- Truth vs. belief must stay visually distinct — anywhere position is shown, the real state and the agent's noisy belief about it are both represented, not collapsed into one.
- Comedy is emergent, not authored — the UI presents what the simulation actually produced (bad navigation, hallucinations, quitting) rather than manufacturing jokes in copy or visuals.
- Build for the audience that's there now — general AI-curious viewers, not ultrarunning insiders — so the UI shouldn't assume trail-running jargon is self-explanatory.
- Speed is a first-class, always-visible dimension of the experience, since the same sim runs at 1x (the real 60h target) and at 60x/600x (dev iteration).

## Accessibility & Inclusion

No product-specific accessibility requirement has been established yet.
