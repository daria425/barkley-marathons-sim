"""Tests for ADR-0008's checkpoint persistence: round-tripping through SQLite/JSON must
reconstruct state exactly — a checkpoint that only "mostly" restores state would make resume
silently diverge from a real continuation.

No pytest-asyncio dependency in this project yet, so async db.py calls are driven with
asyncio.run() directly, same as sim/loop.py's own entrypoint.
"""

import asyncio

import db
from models import Checkpoint, Decision
from sim.frozen_head_state_park import initial_state as park_initial_state
from sim.physiology import initial_state as physio_initial_state


def make_checkpoint(runner_id: str = "test-runner") -> Checkpoint:
    return Checkpoint(
        runner_id=runner_id,
        elapsed_min=123.0,
        physiology=physio_initial_state(),
        environment=park_initial_state(start_hour=6.0, weather="fog"),
        start_hour=6.0,
        true_pos=(36.1, -84.7),
        believed_pos=(36.11, -84.69),
        loop=2,
        books_found=3,
        books_collected_this_loop=[0, 2, 5],
        dist_since_loop_start_km=4.2,
        last_ate_min_ago=15.0,
        last_drank_min_ago=None,
        last_decision=Decision(
            effort=6,
            eat=False,
            drink=True,
            bearing_deg=90.0,
            rest_min=0,
            quit=False,
            monologue="still going",
        ),
        race_config_name="test-race",
        race_config_hash="abc123",
        pending_events=["briar_scratch", "tripped_and_fell"],
        summary_body="Miles 0-10: uneventful.",
        summary_covers_up_to_elapsed_min=100,
    )


def test_checkpoint_save_and_load_round_trips():
    async def scenario():
        conn = await db.init_db(":memory:")
        checkpoint = make_checkpoint()
        await db.save_checkpoint(conn, checkpoint)

        loaded = await db.load_checkpoint(conn, checkpoint.runner_id)

        assert loaded == checkpoint
        await conn.close()

    asyncio.run(scenario())


def test_checkpoint_load_returns_none_when_absent():
    async def scenario():
        conn = await db.init_db(":memory:")
        assert await db.load_checkpoint(conn, "nobody-here") is None
        await conn.close()

    asyncio.run(scenario())


def test_checkpoint_save_replaces_not_appends():
    async def scenario():
        conn = await db.init_db(":memory:")
        first = make_checkpoint()
        await db.save_checkpoint(conn, first)

        second = make_checkpoint().model_copy(update={"elapsed_min": 999.0})
        await db.save_checkpoint(conn, second)

        loaded = await db.load_checkpoint(conn, first.runner_id)
        cursor = await conn.execute(
            "SELECT COUNT(*) FROM checkpoints WHERE runner_id = ?", (first.runner_id,)
        )
        (count,) = await cursor.fetchone()

        assert count == 1
        assert loaded.elapsed_min == 999.0
        await conn.close()

    asyncio.run(scenario())


def test_get_all_turns_returns_full_unlimited_history_oldest_first():
    from tests.test_memory import make_turn

    async def scenario():
        conn = await db.init_db(":memory:")
        runner_id = "test-runner"
        turns = [make_turn(i) for i in range(30)]
        for obs, decision in turns:
            await db.log_turn(conn, runner_id, 36.1, -84.7, obs, decision)

        all_turns = await db.get_all_turns(conn, runner_id)

        assert len(all_turns) == 30
        assert [obs.elapsed_min for obs, _ in all_turns] == list(range(30))
        await conn.close()

    asyncio.run(scenario())
