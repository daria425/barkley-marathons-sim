"""FastAPI app: v1's API surface (CLAUDE.md) — a REST endpoint to start a run, and a
WebSocket streaming live RaceState updates (ticks + brain-call/monologue events) to
however many clients are connected. No frontend yet; verify with websocat or a small script.

setup_observability() must run before `sim.loop` is imported — see observability.py's
docstring for why (agents/participant.py builds its AsyncAnthropic client at import time).
"""

import asyncio
import os

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from observability import setup_observability

setup_observability()

# noqa: E402 below — must follow setup_observability(), see its docstring
from models import CourseBook, CourseGeometry, RaceState  # noqa: E402
from sim import course as course_mod  # noqa: E402
from sim.loop import run  # noqa: E402

app = FastAPI()

_cors_origins = os.environ.get("CORS_ORIGINS", "")
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins.split(",") if _cors_origins else [],
    allow_methods=["*"],
    allow_headers=["*"],
)

_ws_clients: set[WebSocket] = set()
_run_task: asyncio.Task | None = None


async def _broadcast(race_state: RaceState) -> None:
    """Fans a RaceState out to every connected WS client — a dead client just gets dropped
    from the set, not treated as fatal to the sim loop (same spirit as think()'s own
    swallow-and-log-don't-crash contract)."""
    if not _ws_clients:
        return
    payload = race_state.model_dump_json()
    for ws in list(_ws_clients):
        try:
            await ws.send_text(payload)
        except Exception:
            _ws_clients.discard(ws)


@app.get("/")
def health_check():
    return {"status": "ok"}


@app.post("/run")
async def run_ultra_sim(speed: float = 1.0):
    """Kicks off the sim loop as a background task and returns immediately — the sim never
    waits for callers any more than it waits for the LLM. Only one run at a time in v1
    (single-runner, no race-end concept yet, per CLAUDE.md)."""
    global _run_task
    if _run_task is not None and not _run_task.done():
        return {"status": "already running"}
    _run_task = asyncio.create_task(run(speed=speed, on_update=_broadcast))
    return {"status": "started", "speed": speed}


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
    try:
        while True:
            # Nothing incoming to act on yet — just keep the connection open until the
            # client disconnects; state flows one-way out via _broadcast.
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        _ws_clients.discard(websocket)
