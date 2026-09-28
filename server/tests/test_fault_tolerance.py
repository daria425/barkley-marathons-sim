"""Tests for the tick-loop fault-tolerance hardening: run()'s crash boundary must save a
best-effort checkpoint (from the last known-good tick, not the failing one) before re-raising,
so a crash never loses more sim-time than the single tick that caused it. Uses a fake
Participant (no network call) and a monkeypatched DB_PATH (a tmp file, never the real
smoke_test.db) — same reasoning as test_think.py's fakes and ADR-0009's resume tests.
"""

import asyncio

import pytest

import db
import sim.loop as loop_mod
from agents.participant import BrainOutcome


class _FakeParticipant:
    """Stands in for a real Participant — run()/think() only ever call .decide() and read
    .persona.name/.persona off it, never touch the network."""

    def __init__(self, persona):
        self.persona = persona

    async def decide(self, obs, history, summary=""):
        return BrainOutcome(decision=loop_mod.STARTING_DECISION)


def test_crash_boundary_checkpoints_last_good_tick_before_reraising(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _FakeParticipant(persona))

    real_advance_tick = loop_mod.advance_tick
    calls = {"n": 0}

    def flaky_advance_tick(state, decision, dt_min):
        calls["n"] += 1
        if calls["n"] == 3:
            raise RuntimeError("simulated crash")
        return real_advance_tick(state, decision, dt_min)

    monkeypatch.setattr(loop_mod, "advance_tick", flaky_advance_tick)

    with pytest.raises(RuntimeError, match="simulated crash"):
        asyncio.run(loop_mod.run(speed=100_000, duration_min=10))

    # Crashed on the 3rd tick — a checkpoint from the 2nd (last known-good) tick must exist.
    assert calls["n"] == 3

    async def load_saved_checkpoint():
        conn = await db.init_db(db_path)
        runner_id = loop_mod.load_persona(loop_mod.PERSONA_PATH).name
        checkpoint = await db.load_checkpoint(conn, runner_id)
        await conn.close()
        return checkpoint

    checkpoint = asyncio.run(load_saved_checkpoint())
    assert checkpoint is not None
    # 2 successful ticks at TICK_DT_MIN each, elapsed_min starts at 0.
    assert checkpoint.elapsed_min == pytest.approx(2 * loop_mod.TICK_DT_MIN)


class _AlwaysFailingParticipant:
    """Every brain call fails — _compact_and_checkpoint (which only runs after a SUCCESSFUL
    decision) can never fire, isolating the time-based fallback checkpoint as the only thing
    that could possibly save one."""

    def __init__(self, persona):
        self.persona = persona

    async def decide(self, obs, history, summary=""):
        return BrainOutcome(decision=None, failure_reason="simulated outage")


def test_fallback_checkpoint_fires_without_a_successful_brain_decision(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setattr(loop_mod, "DB_PATH", db_path)
    monkeypatch.setattr(loop_mod, "Participant", lambda persona: _AlwaysFailingParticipant(persona))
    monkeypatch.setattr(loop_mod, "FALLBACK_CHECKPOINT_INTERVAL_MIN", loop_mod.TICK_DT_MIN)

    asyncio.run(loop_mod.run(speed=100_000, duration_min=1))

    async def load_saved_checkpoint():
        conn = await db.init_db(db_path)
        runner_id = loop_mod.load_persona(loop_mod.PERSONA_PATH).name
        checkpoint = await db.load_checkpoint(conn, runner_id)
        await conn.close()
        return checkpoint

    checkpoint = asyncio.run(load_saved_checkpoint())
    assert checkpoint is not None
