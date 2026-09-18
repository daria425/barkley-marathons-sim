"""Tests that resume-from-checkpoint (ADR-0008) actually reconstructs the same continuation
a never-interrupted race would have had — the thing that matters, not just "loading doesn't
crash". See ADR-0009 for why this is driven by a scripted Decision list rather than the real
Participant/LLM: it keeps the test fast, free, and deterministic, and isolates the resume
mechanics (which must be bit-exact per ADR-0008) from LLM response variance (which never
could be).
"""

import asyncio
import random

import db
from models import Checkpoint, Decision
from sim.loop import (
    TICK_DT_MIN,
    advance_tick,
    build_initial_state,
    restore_state,
)

SEED = 1234
START_HOUR = 6.0


def _scripted_decisions(n: int) -> list[Decision]:
    """Varied but fixed decisions — effort/eat/drink cycle so physio/park state actually
    changes tick to tick, giving the test something real to compare."""
    return [
        Decision(
            effort=4 + (i % 5),
            eat=(i % 3 == 0),
            drink=(i % 2 == 0),
            bearing_deg=0.0,
            rest_min=0,
            quit=False,
            monologue=f"turn {i}",
        )
        for i in range(n)
    ]


def _run_ticks(state, decisions):
    for decision in decisions:
        advance_tick(state, decision, TICK_DT_MIN)


def _make_checkpoint(state, last_decision: Decision) -> Checkpoint:
    return Checkpoint(
        runner_id="test-runner",
        elapsed_min=state.physio.elapsed_min,
        physiology=state.physio,
        environment=state.park,
        start_hour=state.start_hour,
        true_pos=state.true_pos,
        believed_pos=state.believed_pos,
        loop=state.loop,
        books_found=len(state.books_collected),
        books_collected_this_loop=sorted(state.books_collected),
        dist_since_loop_start_km=state.dist_since_loop_start_km,
        last_ate_min_ago=state.last_ate_min_ago,
        last_decision=last_decision,
        rng_state=db.serialize_rng_state(state.rng),
        summary_text="earlier summary",
        summary_covers_up_to_elapsed_min=0,
    )


def test_resume_continues_bit_exactly_from_a_checkpoint():
    decisions = _scripted_decisions(10)

    # Reference: run straight through, uninterrupted.
    reference_state = build_initial_state(random.Random(SEED), START_HOUR)
    _run_ticks(reference_state, decisions)
    reference_future_draws = [reference_state.rng.random() for _ in range(5)]

    # Split: run the first half, checkpoint, restore, run the second half.
    split_state = build_initial_state(random.Random(SEED), START_HOUR)
    _run_ticks(split_state, decisions[:5])
    checkpoint = _make_checkpoint(split_state, decisions[4])

    resumed_state = restore_state(checkpoint)
    _run_ticks(resumed_state, decisions[5:])
    resumed_future_draws = [resumed_state.rng.random() for _ in range(5)]

    assert resumed_state.physio == reference_state.physio
    assert resumed_state.park == reference_state.park
    assert resumed_state.last_ate_min_ago == reference_state.last_ate_min_ago
    assert resumed_state.true_pos == reference_state.true_pos
    assert resumed_state.believed_pos == reference_state.believed_pos
    assert resumed_state.loop == reference_state.loop
    assert resumed_state.books_collected == reference_state.books_collected
    assert resumed_state.dist_since_loop_start_km == reference_state.dist_since_loop_start_km
    assert resumed_future_draws == reference_future_draws


def test_resume_round_trips_through_real_sqlite_not_just_in_memory_objects():
    """Same as above, but the checkpoint actually goes through db.save_checkpoint /
    load_checkpoint — closes the gap between "Checkpoint objects round-trip through JSON"
    (tests/test_db.py) and "loop.py's restore_state produces a working continuation"."""
    decisions = _scripted_decisions(10)

    reference_state = build_initial_state(random.Random(SEED), START_HOUR)
    _run_ticks(reference_state, decisions)

    async def scenario():
        conn = await db.init_db(":memory:")
        split_state = build_initial_state(random.Random(SEED), START_HOUR)
        _run_ticks(split_state, decisions[:5])
        await db.save_checkpoint(conn, _make_checkpoint(split_state, decisions[4]))

        loaded = await db.load_checkpoint(conn, "test-runner")
        resumed_state = restore_state(loaded)
        _run_ticks(resumed_state, decisions[5:])
        await conn.close()
        return resumed_state

    resumed_state = asyncio.run(scenario())

    assert resumed_state.physio == reference_state.physio
    assert resumed_state.park == reference_state.park
