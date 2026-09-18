"""Tests for ADR-0008's checkpoint persistence: round-tripping through SQLite/JSON must
reconstruct state exactly, including rng state — a checkpoint that only "mostly" restores
state would make resume silently diverge from a real continuation.

No pytest-asyncio dependency in this project yet, so async db.py calls are driven with
asyncio.run() directly, same as sim/loop.py's own entrypoint.
"""

import asyncio
import random

import db
from models import Checkpoint, Decision
from sim.frozen_head_state_park import initial_state as park_initial_state
from sim.physiology import initial_state as physio_initial_state


def make_checkpoint(runner_id: str = "test-runner", rng: random.Random | None = None) -> Checkpoint:
    rng = rng or random.Random(42)
    return Checkpoint(
        runner_id=runner_id,
        elapsed_min=123.0,
        physiology=physio_initial_state(),
        environment=park_initial_state(start_hour=6.0, rng=rng),
        start_hour=6.0,
        true_pos=(36.1, -84.7),
        believed_pos=(36.11, -84.69),
        loop=2,
        books_found=3,
        last_ate_min_ago=15.0,
        last_decision=Decision(
            effort=6,
            eat=False,
            drink=True,
            bearing_deg=90.0,
            rest_min=0,
            quit=False,
            monologue="still going",
        ),
        rng_state=db.serialize_rng_state(rng),
        summary_text="Miles 0-10: uneventful.",
        summary_covers_up_to_elapsed_min=100,
    )


def test_rng_state_round_trips_through_json_as_a_real_tuple():
    """random.setstate() requires the internal-state field to be an actual tuple, not a list
    — a bare json.dumps/loads round-trip would silently hand it a list instead. This is the
    exact bug serialize/deserialize_rng_state exist to avoid."""
    rng = random.Random(7)
    rng.random()  # advance state so we're not just testing the fresh-seed case
    state_json = db.serialize_rng_state(rng)

    restored = db.rng_from_state(state_json)

    assert rng.getstate() == restored.getstate()
    # and the restored rng actually produces the same future sequence, not just equal state
    assert [rng.random() for _ in range(5)] == [restored.random() for _ in range(5)]


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
            await db.log_turn(conn, runner_id, obs, decision)

        all_turns = await db.get_all_turns(conn, runner_id)

        assert len(all_turns) == 30
        assert [obs.elapsed_min for obs, _ in all_turns] == list(range(30))
        await conn.close()

    asyncio.run(scenario())
