"""The operator kill switch (ADR-0022): stop_event ends the race as an ordinary dnf_cutoff.

Engine tests drive run() with a fake Participant and a tmp DB (same approach as
test_fault_tolerance.py); the endpoint test goes through POST /run + POST /stop at speed=1, where
a tick is a 30s sleep — so it only passes quickly if that sleep is genuinely interruptible.
"""

import asyncio
import time

from fastapi.testclient import TestClient

import db
import main
import sim.loop as loop_mod
from agents.participant import BrainOutcome
from models import Decision


class _SlowParticipant:
    """A brain call that would take 60s — if stopping doesn't cancel it, run() blocks on it."""

    def __init__(self, persona):
        self.persona = persona
        self.calls = 0

    async def decide(self, obs, history, summary_body="", latest_highlight=""):
        self.calls += 1
        await asyncio.sleep(60)
        return BrainOutcome(decision=loop_mod.STARTING_DECISION)


def _load_checkpoint(db_path: str):
    async def go():
        conn = await db.init_db(db_path)
        runner_id = loop_mod.load_persona(loop_mod.PERSONA_PATH).name
        checkpoint = await db.load_checkpoint(conn, runner_id)
        await conn.close()
        return checkpoint

    return asyncio.run(go())


def test_check_race_end_killed_means_dnf_cutoff_but_real_outcomes_win():
    state = loop_mod.build_initial_state(__import__("random").Random(1), 6.0)
    assert loop_mod._check_race_end(state, loop_mod.STARTING_DECISION, killed=True) == "dnf_cutoff"
    assert loop_mod._check_race_end(state, loop_mod.STARTING_DECISION, killed=False) is None

    quit_decision = Decision(
        **{**loop_mod.STARTING_DECISION.model_dump(), "quit": True, "monologue": "nope"}
    )
    assert loop_mod._check_race_end(state, quit_decision, killed=True) == "dnf_quit"
    state.loop = loop_mod.TOTAL_LOOPS + 1
    assert loop_mod._check_race_end(state, loop_mod.STARTING_DECISION, killed=True) == "finished"


def test_stop_event_ends_run_as_dnf_cutoff_and_cancels_in_flight_brain_calls(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    participant = {}

    def make(persona):
        participant["p"] = _SlowParticipant(persona)
        return participant["p"]

    monkeypatch.setattr(loop_mod, "Participant", make)

    stop = asyncio.Event()
    updates = []

    async def on_update(race_state):
        updates.append(race_state)
        if len(updates) == 4:
            stop.set()

    started = time.monotonic()
    asyncio.run(loop_mod.run(speed=1000, duration_min=600, on_update=on_update, stop_event=stop))
    took = time.monotonic() - started

    assert took < 5  # not blocked on the 60s brain calls, nor on the rest of a 600-minute race
    last = updates[-1]
    assert next(iter(last.runners.values())).status == "dnf_cutoff"
    assert last.elapsed_min < 10  # a few ticks in, nowhere near the 600-minute duration
    assert participant["p"].calls >= 1  # brain calls were in flight and got cancelled
    checkpoint = _load_checkpoint(db_path)
    assert checkpoint.status == "dnf_cutoff"

    # the ended checkpoint is what keeps a stopped run from being resumed and spending again
    before = len(updates)
    asyncio.run(loop_mod.run(speed=1000, duration_min=600, on_update=on_update))
    assert len(updates) == before + 1  # re-announced once, no tick loop


def test_post_stop_ends_a_live_run_promptly_and_viewers_see_a_plain_dnf_cutoff(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(loop_mod, "DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _SlowParticipant(persona))
    monkeypatch.setattr(main, "RACE_ADMIN_TOKEN", "secret")
    monkeypatch.setattr(main, "_latest_race_state", None)
    headers = {"x-admin-token": "secret"}

    with TestClient(main.app) as client:
        assert client.post("/stop", headers=headers).json() == {"status": "not running"}
        assert client.post("/stop").status_code == 401  # admin-token gated like /run

        assert client.post("/run?speed=1&duration_min=600", headers=headers).json()["status"] == (
            "started"
        )
        deadline = time.monotonic() + 5
        while client.get("/status").json()["last_tick_elapsed_min"] is None:
            assert time.monotonic() < deadline, "run never ticked"
            time.sleep(0.05)

        started = time.monotonic()
        assert client.post("/stop", headers=headers).json() == {"status": "stopped"}
        assert time.monotonic() - started < 5  # mid-way through a 30s tick sleep

        public = client.get("/status").json()
        assert public["running"] is False
        assert "stop" not in str(public).lower() and "kill" not in str(public).lower()
        runner = next(iter(main._latest_race_state.runners.values()))
        assert runner.status == "dnf_cutoff"

        assert client.post("/stop", headers=headers).json() == {"status": "not running"}
