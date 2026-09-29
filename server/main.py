"""FastAPI app: v1's API surface (CLAUDE.md) — a REST endpoint to start a run, and a
WebSocket streaming live RaceState updates (ticks + brain-call/monologue events) to
however many clients are connected. No frontend yet; verify with websocat or a small script.

setup_observability() must run before `sim.loop` is imported — see observability.py's
docstring for why (agents/participant.py builds its AsyncAnthropic client at import time).
"""

import asyncio
import logging
import os
import secrets
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, Header, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from observability import setup_observability

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger(__name__)

setup_observability()

# noqa: E402 below — must follow setup_observability(), see its docstring
from models import CourseBook, CourseGeometry, RaceState  # noqa: E402
from sim import course as course_mod  # noqa: E402
from sim.loop import FULL_RACE_MINUTES, run  # noqa: E402

# How many consecutive run() crashes with zero sim-time progress the supervisor tolerates
# before giving up — a transient hiccup (DB lock, a one-off bad state) gets retried, a
# persistent bug (crashes before a single tick completes) doesn't spin forever.
MAX_CONSECUTIVE_FAILURES = 5
RESTART_BACKOFF_SEC = 5

# The one costly, state-changing endpoint (POST /run kicks off a 60h race, real Anthropic
# spend) is gated behind a single shared secret, not real auth — there's one operator (you),
# not users/sessions. Same ".env, gitignored, mirrored as a Fly.io secret" convention as
# ANTHROPIC_API_KEY (CLAUDE.md's Conventions). No token set means fail CLOSED (nobody can
# start a run), not open.
RACE_ADMIN_TOKEN = os.environ.get("RACE_ADMIN_TOKEN", "")


def require_admin_token(x_admin_token: str = Header(default="")) -> None:
    """FastAPI dependency guarding POST /run. secrets.compare_digest avoids a timing
    side-channel on the comparison; a plain `==` leaks how many leading characters matched
    through response latency."""
    if not RACE_ADMIN_TOKEN or not secrets.compare_digest(x_admin_token, RACE_ADMIN_TOKEN):
        raise HTTPException(status_code=401, detail="invalid or missing admin token")


# Populated by _broadcast (every tick) and _supervised_run (on crash/restart) — backs /status.
_health: dict = {
    "alive": False,
    "last_tick_elapsed_min": None,
    "last_tick_at": None,
    "restart_count": 0,
    "last_error": None,
}

app = FastAPI()

_raw_cors_origins = os.environ.get("CORS_ORIGINS", "").split(",")
_cors_origins = [origin.strip() for origin in _raw_cors_origins if origin.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_ws_clients: set[WebSocket] = set()
_run_task: asyncio.Task | None = None
# Last RaceState broadcast, replayed to a client the instant it connects — otherwise a
# newly-opened tab sees an empty store (frontend renders IdleState) until the next tick's
# broadcast fires, which at speed=1 can be up to 15s away.
_latest_race_state: RaceState | None = None


async def _broadcast(race_state: RaceState) -> None:
    """Fans a RaceState out to every connected WS client — a dead client just gets dropped
    from the set, not treated as fatal to the sim loop (same spirit as think()'s own
    swallow-and-log-don't-crash contract). Also the one place every tick already passes
    through, so it doubles as the liveness signal /status reports."""
    global _latest_race_state
    _latest_race_state = race_state
    _health["last_tick_elapsed_min"] = race_state.elapsed_min
    _health["last_tick_at"] = datetime.now(UTC).isoformat()
    if not _ws_clients:
        return
    payload = race_state.model_dump_json()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            _ws_clients.discard(ws)


async def _supervised_run(speed: float, duration_min: float) -> None:
    """Wraps sim.loop.run() with crash-restart. run()'s own crash boundary (sim/loop.py)
    checkpoints best-effort before re-raising, and db.load_checkpoint (ADR-0008) means a fresh
    run() call resumes right where the last one left off — so on a crash, this just calls
    run() again rather than losing the race. Keeps calling until `duration_min` of sim-time
    has actually elapsed (tracked via _health, updated every tick by _broadcast) or too many
    crashes happen in a row with zero progress."""
    remaining = duration_min
    consecutive_failures = 0
    _health["alive"] = True
    try:
        while remaining > 0:
            start_elapsed = _health["last_tick_elapsed_min"] or 0.0
            try:
                await run(speed=speed, duration_min=remaining, on_update=_broadcast)
                return
            except Exception as e:
                last_elapsed = _health["last_tick_elapsed_min"] or start_elapsed
                progressed = last_elapsed - start_elapsed
                remaining -= progressed
                consecutive_failures = 0 if progressed > 0 else consecutive_failures + 1
                _health["restart_count"] += 1
                _health["last_error"] = f"{type(e).__name__}: {e}"
                logger.info(
                    "[supervisor] run() crashed (%s); %.1f sim-min remaining, %d consecutive "
                    "failure(s) with no progress",
                    _health["last_error"],
                    remaining,
                    consecutive_failures,
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.info(
                        "[supervisor] giving up after %d consecutive failures with no "
                        "progress — last checkpoint is intact for inspection",
                        MAX_CONSECUTIVE_FAILURES,
                    )
                    return
                await asyncio.sleep(RESTART_BACKOFF_SEC)
    finally:
        _health["alive"] = False


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/run", dependencies=[Depends(require_admin_token)])
async def run_ultra_sim(speed: float = 1.0, duration_min: float = FULL_RACE_MINUTES):
    """Kicks off the sim loop as a background task and returns immediately — the sim never
    waits for callers any more than it waits for the LLM. Only one run at a time in v1
    (single-runner, no race-end concept yet, per CLAUDE.md). duration_min defaults to the full
    60h race; pass a smaller value for a bounded live canary. Requires the X-Admin-Token
    header (see require_admin_token) — this is the one endpoint that costs real money and
    starts a race other people can watch, so it isn't left open to anyone who finds the URL."""
    global _run_task
    if _run_task is not None and not _run_task.done():
        return {"status": "already running"}
    _run_task = asyncio.create_task(_supervised_run(speed=speed, duration_min=duration_min))
    return {"status": "started", "speed": speed, "duration_min": duration_min}


@app.get("/status")
async def status():
    """Liveness for an unattended multi-hour run — is the sim task alive, when did it last
    tick, and has the crash-restart supervisor (_supervised_run) had to kick in."""
    return {
        "running": _run_task is not None and not _run_task.done(),
        **_health,
    }


@app.get("/course", response_model=CourseGeometry)
async def course_geometry():
    """Static course shape for the frontend map — trail polyline + book locations. Not part
    of the WS stream: sim.course.load_course() is lru_cached and doesn't change mid-race, so
    the frontend fetches this once rather than getting it re-broadcast every tick."""
    course = course_mod.load_course()
    return CourseGeometry(
        points=[(p.lat, p.lon) for p in course.points],
        books=[CourseBook(index=b.index, name=b.name, lat=b.lat, lon=b.lon) for b in course.books],
    )


_SCHEMA_MODELS = {"race-state": RaceState}


@app.get("/schema", response_model=RaceState)
async def schema_export(model: str):
    """Schema-export-only — never actually returns 200. FastAPI doesn't document WebSocket
    payloads in /openapi.json at all, and RaceState only ever flows over /ws, so without this
    route openapi-typescript would generate nothing for it (ADR-0011/CLAUDE.md's Type sync
    note: never hand-write duplicate TS types). `response_model=RaceState` is what puts its
    schema into /openapi.json's components — the handler itself is never meant to succeed.
    `model` is a query param (not a path segment) so future WS-only models can reuse this
    same route instead of getting one route each."""
    if model not in _SCHEMA_MODELS:
        raise HTTPException(status_code=404, detail=f"unknown schema model: {model!r}")
    raise HTTPException(status_code=404, detail="schema-export endpoint; not for runtime use")


@app.websocket("/ws")
async def ws_endpoint(websocket: WebSocket):
    await websocket.accept()
    _ws_clients.add(websocket)
    if _latest_race_state is not None:
        try:
            await websocket.send_text(_latest_race_state.model_dump_json())
        except Exception:
            _ws_clients.discard(websocket)
            return
    try:
        while True:
            # Nothing incoming to act on yet — just keep the connection open until the
            # client disconnects; state flows one-way out via _broadcast.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
