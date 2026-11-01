"""Tests that resume-from-checkpoint (ADR-0008) actually reconstructs the same continuation
a never-interrupted race would have had — the thing that matters, not just "loading doesn't
crash". See ADR-0009 for why this is driven by a scripted Decision list rather than the real
Participant/LLM: it keeps the test fast, free, and deterministic, and isolates the resume
mechanics (which must be bit-exact per ADR-0008) from LLM response variance (which never
could be).

Also home to ADR-0024's determinism properties, since they're the same kind of scripted-decision
comparison: a race config must hand every run the same conditions whatever the runner does.
"""

import asyncio

import pytest
from race_config_helpers import make_race_config

import db
from models import Checkpoint, Decision
from sim.loop import (
    TICK_DT_MIN,
    RaceConfigMismatch,
    advance_tick,
    build_initial_state,
    restore_state,
)
from sim.race_config import config_hash

# Events/hallucinations inside the 10-tick (5 sim-min) window the resume tests run, so resume
# has to carry the schedule across the split too.
CONFIG = make_race_config(
    events=[(1.0, "briar_scratch"), (3.0, "tripped_and_fell"), (4.0, "stepped_in_puddle")],
    hallucinations=[(3.5, "The trees are whispering your name.")],
)


def _scripted_decisions(n: int, bearing_deg: float = 0.0) -> list[Decision]:
    """Varied but fixed decisions — effort/eat/drink cycle so physio/park state actually
    changes tick to tick, giving the test something real to compare."""
    return [
        Decision(
            effort=4 + (i % 5),
            eat=(i % 3 == 0),
            drink=(i % 2 == 0),
            bearing_deg=bearing_deg,
            rest_min=0,
            quit=False,
            monologue=f"turn {i}",
        )
        for i in range(n)
    ]


def _run_ticks(state, decisions):
    return [advance_tick(state, decision, TICK_DT_MIN) for decision in decisions]


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
        last_drank_min_ago=state.last_drank_min_ago,
        last_decision=last_decision,
        race_config_name=state.race_config.name,
        race_config_hash=config_hash(state.race_config),
        pending_events=list(state.pending_events),
        summary_body="earlier summary",
        summary_covers_up_to_elapsed_min=0,
    )


def _assert_same_state(resumed_state, reference_state):
    assert resumed_state.physio == reference_state.physio
    assert resumed_state.park == reference_state.park
    assert resumed_state.last_ate_min_ago == reference_state.last_ate_min_ago
    assert resumed_state.last_drank_min_ago == reference_state.last_drank_min_ago
    assert resumed_state.true_pos == reference_state.true_pos
    assert resumed_state.believed_pos == reference_state.believed_pos
    assert resumed_state.loop == reference_state.loop
    assert resumed_state.books_collected == reference_state.books_collected
    assert resumed_state.dist_since_loop_start_km == reference_state.dist_since_loop_start_km
    assert resumed_state.pending_events == reference_state.pending_events


def test_resume_continues_bit_exactly_from_a_checkpoint():
    decisions = _scripted_decisions(10)

    # Reference: run straight through, uninterrupted.
    reference_state = build_initial_state(CONFIG)
    reference_obs = _run_ticks(reference_state, decisions)

    # Split: run the first half, checkpoint, restore, run the second half.
    split_state = build_initial_state(CONFIG)
    split_obs = _run_ticks(split_state, decisions[:5])
    checkpoint = _make_checkpoint(split_state, decisions[4])

    resumed_state = restore_state(checkpoint, CONFIG)
    split_obs += _run_ticks(resumed_state, decisions[5:])

    _assert_same_state(resumed_state, reference_state)
    assert split_obs == reference_obs


def test_resume_round_trips_through_real_sqlite_not_just_in_memory_objects():
    """Same as above, but the checkpoint actually goes through db.save_checkpoint /
    load_checkpoint — closes the gap between "Checkpoint objects round-trip through JSON"
    (tests/test_db.py) and "loop.py's restore_state produces a working continuation"."""
    decisions = _scripted_decisions(10)

    reference_state = build_initial_state(CONFIG)
    _run_ticks(reference_state, decisions)

    async def scenario():
        conn = await db.init_db(":memory:")
        split_state = build_initial_state(CONFIG)
        _run_ticks(split_state, decisions[:5])
        await db.save_checkpoint(conn, _make_checkpoint(split_state, decisions[4]))

        loaded = await db.load_checkpoint(conn, "test-runner")
        resumed_state = restore_state(loaded, CONFIG)
        _run_ticks(resumed_state, decisions[5:])
        await conn.close()
        return resumed_state

    resumed_state = asyncio.run(scenario())

    _assert_same_state(resumed_state, reference_state)


def test_resume_is_refused_under_an_edited_race_config():
    state = build_initial_state(CONFIG)
    _run_ticks(state, _scripted_decisions(3))
    checkpoint = _make_checkpoint(state, _scripted_decisions(1)[0])

    edited = CONFIG.model_copy(update={"start_hour": 7.0})
    with pytest.raises(RaceConfigMismatch):
        restore_state(checkpoint, edited)
    renamed = CONFIG.model_copy(update={"name": "other-race"})
    with pytest.raises(RaceConfigMismatch):
        restore_state(checkpoint, renamed)


def test_conditions_are_identical_whatever_the_runner_decides():
    """ADR-0024's core property: with the same config, two runners heading opposite ways at
    different efforts still get the same weather, the same scheduled events in the same order,
    and the same hallucinations at the same minutes. With v1's single shared rng, terrain-gated
    event rolls made these drift apart as soon as the paths did."""
    config = make_race_config(
        events=[(t, e) for t in range(5, 200, 15) for e in ["briar_scratch"]],
        hallucinations=[(7.0, "a"), (130.0, "b"), (241.0, "c")],
    )
    north = build_initial_state(config)
    south = build_initial_state(config)
    north_obs = _run_ticks(north, _scripted_decisions(600, bearing_deg=0.0))
    south_obs = _run_ticks(south, _scripted_decisions(600, bearing_deg=180.0))

    assert north.true_pos != south.true_pos  # the runners really did diverge
    assert [o.weather for o in north_obs] == [o.weather for o in south_obs]
    assert [o.hallucination for o in north_obs] == [o.hallucination for o in south_obs]
    assert {o.weather for o in north_obs} == {"clear", "fog", "rain"}

    def scheduled(observations):
        return [o.event for o in observations if o.event not in (None, "found_book")]

    # same events, same order, all of them delivered (a found_book tick may shift one by a tick)
    assert scheduled(north_obs) == scheduled(south_obs) == [e.event for e in config.events]


def test_same_config_and_decisions_reproduce_the_whole_run():
    decisions = _scripted_decisions(200)
    first = _run_ticks(build_initial_state(CONFIG), decisions)
    second = _run_ticks(build_initial_state(CONFIG), decisions)
    assert first == second


def test_gps_noise_depends_on_seed():
    decisions = _scripted_decisions(20)
    a = _run_ticks(build_initial_state(CONFIG), decisions)
    b = _run_ticks(build_initial_state(CONFIG.model_copy(update={"seed": 99})), decisions)
    assert [o.gps_guess for o in a] != [o.gps_guess for o in b]
    assert [o.weather for o in a] == [o.weather for o in b]  # nothing else moved


def test_eat_and_drink_counters_start_unset_reset_on_the_tick_and_then_count_up():
    def decide(eat=False, drink=False):
        return Decision(
            effort=5, eat=eat, drink=drink, bearing_deg=0.0, rest_min=0, quit=False, monologue=""
        )

    state = build_initial_state(CONFIG)
    obs = advance_tick(state, decide(), TICK_DT_MIN)
    assert (obs.last_ate_min_ago, obs.last_drank_min_ago) == (None, None)
    obs = advance_tick(state, decide(eat=True), TICK_DT_MIN)
    assert (obs.last_ate_min_ago, obs.last_drank_min_ago) == (0.0, None)
    obs = advance_tick(state, decide(drink=True), TICK_DT_MIN)
    assert (obs.last_ate_min_ago, obs.last_drank_min_ago) == (TICK_DT_MIN, 0.0)
