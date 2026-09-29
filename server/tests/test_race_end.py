"""Tests for ADR-0019's race-end mechanism: a runner's status moves from "running" to exactly
one of "finished" / "dnf_cutoff" / "dnf_quit", the tick loop stops as soon as that happens, the
terminal state is broadcast and checkpointed, and a resumed process never re-ticks an
already-ended race. Uses fake Participants (no network call) and a monkeypatched DB_PATH — same
reasoning as test_fault_tolerance.py/test_think.py's fakes and ADR-0009's resume tests.
"""

import asyncio
import random

import pytest

import db
import sim.loop as loop_mod
from agents.participant import BrainOutcome
from models import Decision
from sim.loop import STARTING_DECISION, _check_race_end, build_initial_state
from sim.sim_constants import TOTAL_LOOPS


def test_check_race_end_running_when_neither_condition_holds():
    state = build_initial_state(random.Random(1), start_hour=6.0)
    assert _check_race_end(state, STARTING_DECISION) is None


def test_check_race_end_detects_quit():
    state = build_initial_state(random.Random(1), start_hour=6.0)
    quit_decision = Decision(
        effort=5, eat=False, drink=False, bearing_deg=0.0, rest_min=0, quit=True, monologue="done"
    )
    assert _check_race_end(state, quit_decision) == "dnf_quit"


def test_check_race_end_detects_finished():
    state = build_initial_state(random.Random(1), start_hour=6.0)
    state.loop = TOTAL_LOOPS + 1
    assert _check_race_end(state, STARTING_DECISION) == "finished"


def test_check_race_end_prioritizes_finished_over_quit():
    """A runner who completes the last loop on the same tick they'd have quit finishes, not
    DNFs — see _check_race_end's docstring on the priority order."""
    state = build_initial_state(random.Random(1), start_hour=6.0)
    state.loop = TOTAL_LOOPS + 1
    quit_decision = Decision(
        effort=5, eat=False, drink=False, bearing_deg=0.0, rest_min=0, quit=True, monologue="done"
    )
    assert _check_race_end(state, quit_decision) == "finished"


class _AlwaysQuitParticipant:
    """Every decide() call hands back a quit=True decision — stands in for a real Participant,
    same shape as test_fault_tolerance.py's fakes."""

    def __init__(self, persona):
        self.persona = persona

    async def decide(self, obs, history, summary_body="", latest_highlight=""):
        return BrainOutcome(
            decision=Decision(
                effort=5,
                eat=False,
                drink=False,
                bearing_deg=0.0,
                rest_min=0,
                quit=True,
                monologue="had enough",
            )
        )


class _NeverQuitParticipant:
    """Always hands back the inert starting decision — never triggers a finish or a quit, so
    the only way its race can end is duration_min running out (dnf_cutoff)."""

    def __init__(self, persona):
        self.persona = persona

    async def decide(self, obs, history, summary_body="", latest_highlight=""):
        return BrainOutcome(decision=STARTING_DECISION)


def _load_checkpoint(db_path: str):
    async def scenario():
        conn = await db.init_db(db_path)
        runner_id = loop_mod.load_persona(loop_mod.PERSONA_PATH).name
        checkpoint = await db.load_checkpoint(conn, runner_id)
        await conn.close()
        return checkpoint

    return asyncio.run(scenario())


def test_run_stops_early_and_marks_dnf_quit_when_decision_says_quit(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _AlwaysQuitParticipant(persona))

    # Generous duration_min — the assertion is that the race ends well before exhausting it,
    # not on an exact tick count (the async think() round-trip that delivers quit=True isn't
    # pinned to a specific tick, same caveat as test_fault_tolerance.py's exact-tick tests).
    asyncio.run(loop_mod.run(speed=100_000, duration_min=600))

    checkpoint = _load_checkpoint(db_path)
    assert checkpoint is not None
    assert checkpoint.status == "dnf_quit"
    assert checkpoint.elapsed_min < 600


def test_run_marks_dnf_cutoff_when_duration_min_exhausted(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _NeverQuitParticipant(persona))

    asyncio.run(loop_mod.run(speed=100_000, duration_min=1.0))

    checkpoint = _load_checkpoint(db_path)
    assert checkpoint is not None
    assert checkpoint.status == "dnf_cutoff"
    assert checkpoint.elapsed_min == pytest.approx(1.0)


def test_run_does_not_re_tick_an_already_ended_race_on_resume(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _NeverQuitParticipant(persona))

    asyncio.run(loop_mod.run(speed=100_000, duration_min=1.0))
    ended_checkpoint = _load_checkpoint(db_path)
    assert ended_checkpoint.status == "dnf_cutoff"

    updates: list = []

    async def collect(race_state):
        updates.append(race_state)

    # Same duration_min again — a real re-tick would advance elapsed_min by another 1.0.
    asyncio.run(loop_mod.run(speed=100_000, duration_min=1.0, on_update=collect))

    resumed_checkpoint = _load_checkpoint(db_path)
    assert resumed_checkpoint.elapsed_min == ended_checkpoint.elapsed_min

    assert len(updates) == 1
    runner_state = next(iter(updates[0].runners.values()))
    assert runner_state.status == "dnf_cutoff"
    assert updates[0].elapsed_min == pytest.approx(ended_checkpoint.elapsed_min)
