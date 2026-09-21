"""FastAPI app: v1's API surface (CLAUDE.md) — a REST endpoint to start a run, and a
WebSocket streaming live RaceState updates (ticks + brain-call/monologue events) to
however many clients are connected. No frontend yet; verify with websocat or a small script.

setup_observability() must run before `sim.loop` is imported — see observability.py's
docstring for why (agents/participant.py builds its AsyncAnthropic client at import time).
"""

import asyncio
import os

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from observability import setup_observability

setup_observability()

from models import RaceState  # noqa: E402 (must follow setup_observability(), see docstring)
from sim.loop import run  # noqa: E402 (must follow setup_observability(), see docstring)

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
