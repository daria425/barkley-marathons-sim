"""Tests for think()'s side of CLAUDE.md's failure contract: a failed brain call (a
BrainOutcome with decision=None) must leave runner.decision untouched and must NOT write a
checkpoint or compact memory for that tick — there's no new decision to checkpoint. A
successful call must do both, and a failure must still be persisted (db.log_turn's
failure_reason column) rather than only ever reaching a print() line. Uses a fake Participant
(no network call) so this is fast/deterministic — same reasoning as ADR-0009's resume tests,
applied to the failure path instead of the resume path.
"""

import asyncio
import random
from types import SimpleNamespace

import db
from agents.participant import BrainOutcome
from models import Decision
from sim.loop import (
    STARTING_DECISION,
    RunnerLoop,
    StateSnapshot,
    advance_tick,
    build_initial_state,
    think,
)


class _FakeParticipant:
    """Stands in for a real Participant — think() only ever calls .decide() and reads
    .persona.name off it."""

    def __init__(self, name: str, outcome: BrainOutcome):
        self.persona = SimpleNamespace(name=name)
        self._outcome = outcome

    async def decide(self, obs, history, summary=""):
        return self._outcome


def _snapshot(state) -> StateSnapshot:
    return StateSnapshot(
        physio=state.physio,
        park=state.park,
        start_hour=state.start_hour,
        true_pos=state.true_pos,
        believed_pos=state.believed_pos,
        loop=state.loop,
        books_collected=state.books_collected,
        dist_since_loop_start_km=state.dist_since_loop_start_km,
        last_ate_min_ago=state.last_ate_min_ago,
        rng_state=db.serialize_rng_state(state.rng),
    )


def test_think_keeps_old_decision_and_skips_checkpoint_on_failed_brain_call(capsys):
    failure = BrainOutcome(decision=None, failure_reason="RuntimeError: simulated outage")

    async def scenario():
        conn = await db.init_db(":memory:")
        runner = RunnerLoop(_FakeParticipant("Hank", failure), conn, asyncio.Semaphore(5))
        state = build_initial_state(random.Random(1), start_hour=6.0)
        obs = advance_tick(state, STARTING_DECISION, dt_min=0.1)

        await think(runner, obs, _snapshot(state))

        assert runner.decision is STARTING_DECISION
        assert await db.load_checkpoint(conn, "Hank") is None
        failures = await db.get_failures(conn, "Hank")
        assert failures == [(obs.elapsed_min, "RuntimeError: simulated outage")]
        await conn.close()

    asyncio.run(scenario())
    assert "mumbles incoherently" in capsys.readouterr().out


def test_think_updates_decision_and_checkpoints_on_successful_brain_call():
    new_decision = Decision(
        effort=7,
        eat=True,
        drink=False,
        bearing_deg=10.0,
        rest_min=0,
        quit=False,
        monologue="pushing on",
    )

    async def scenario():
        conn = await db.init_db(":memory:")
        outcome = BrainOutcome(decision=new_decision)
        runner = RunnerLoop(_FakeParticipant("Hank", outcome), conn, asyncio.Semaphore(5))
        state = build_initial_state(random.Random(1), start_hour=6.0)
        obs = advance_tick(state, STARTING_DECISION, dt_min=0.1)

        await think(runner, obs, _snapshot(state))

        assert runner.decision == new_decision
        checkpoint = await db.load_checkpoint(conn, "Hank")
        assert checkpoint is not None
        assert checkpoint.last_decision == new_decision
        assert await db.get_failures(conn, "Hank") == []
        await conn.close()

    asyncio.run(scenario())


class _RaisingParticipant:
    """Simulates a failure that ISN'T decide()'s own internal try/except — e.g. a bug
    somewhere else in think()'s try block. Exercises the outer except in think(), which has
    to persist a failure_reason itself since there's no BrainOutcome to carry one."""

    def __init__(self, name: str):
        self.persona = SimpleNamespace(name=name)

    async def decide(self, obs, history, summary=""):
        raise ValueError("something else broke")


def test_think_persists_a_failure_reason_even_for_the_outer_except_path(capsys):
    async def scenario():
        conn = await db.init_db(":memory:")
        runner = RunnerLoop(_RaisingParticipant("Hank"), conn, asyncio.Semaphore(5))
        state = build_initial_state(random.Random(1), start_hour=6.0)
        obs = advance_tick(state, STARTING_DECISION, dt_min=0.1)

        await think(runner, obs, _snapshot(state))

        assert runner.decision is STARTING_DECISION
        failures = await db.get_failures(conn, "Hank")
        assert failures == [(obs.elapsed_min, "ValueError: something else broke")]
        await conn.close()

    asyncio.run(scenario())
    assert "mumbles incoherently" in capsys.readouterr().out
