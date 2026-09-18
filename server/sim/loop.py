"""Vertical-slice smoke test loop (ADR-0005) — proves Observation -> Decision -> monologue
works end to end before sim/course.py exists for real.

Course-dependent Observation fields (position, terrain, books, bearing) are hardcoded stubs
here, not read from a real course — see ADR-0005. Everything else (physiology, weather,
memory, logging) is the real thing.
"""

import asyncio
import random
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import aiosqlite
import gpxpy
from langfuse import propagate_attributes

import db
from agents.memory import SLIDING_WINDOW_N, compact_if_needed
from agents.participant import Participant
from agents.personas import load_persona
from models import Checkpoint, Decision, Observation
from sim import frozen_head_state_park, physiology
from sim.sim_utils import format_clock_time

# TICK_DT_MIN lowered from ADR-0005's 0.25 to 0.1 for this run only, to get enough decisions
# (10 instead of 4) to cross agents/memory.py's SLIDING_WINDOW_N — real wall-clock duration is
# TOTAL_SIM_MINUTES * 60s regardless of tick granularity, so this still runs in ~1 real minute.
TICK_DT_MIN = 0.1
TOTAL_SIM_MINUTES = 1.0
DB_PATH = "smoke_test.db"
PERSONA_PATH = Path(__file__).parent.parent / "agents" / "personas" / "barkley_expert.yaml"
GPX_PATH = Path(__file__).parent.parent / "files" / "Barkley_Challenge_Loop_FKT.gpx"

BASE_HR = 60
BASE_PACE_MIN_PER_KM = 10.0  # untuned placeholder, see ADR-0004's tuning note

# Stubbed course state (ADR-0005) — replaced once sim/course.py exists for real
STUB_TERRAIN = "gravel road, gentle climb"
STUB_LOOP = 1
STUB_BOOKS_FOUND = 0
STUB_BEARING_DEG = 0.0

STARTING_DECISION = Decision(
    effort=5,
    eat=False,
    drink=False,
    bearing_deg=STUB_BEARING_DEG,
    rest_min=0,
    quit=False,
    monologue="(standing at the start line)",
)


class RunnerLoop:
    """Mutable per-runner loop state. `decision` is updated in place by think() tasks —
    matches CLAUDE.md's think(runner)/loop() pseudocode, where the sim loop always reads
    runner.decision rather than waiting on the brain call that's updating it."""

    def __init__(
        self, participant: Participant, conn: aiosqlite.Connection, sem: asyncio.Semaphore
    ):
        self.participant = participant
        self.runner_id = participant.persona.name
        self.conn = conn
        self.sem = sem
        self.decision = STARTING_DECISION
        # ADR-0008: running compacted summary + how far it reaches. Defaults are the
        # fresh-start case; run() overwrites both from the checkpoint when resuming.
        self.summary = ""
        self.summary_covers_up_to_elapsed_min = 0


@dataclass(frozen=True)
class StateSnapshot:
    """Everything a Checkpoint (ADR-0008) needs beyond the Observation/Decision pair, captured
    at the same tick as the Observation it accompanies — same late-binding reasoning as obs
    itself (see think()'s docstring): the loop's physio/park/rng keep advancing on every tick,
    so this must be passed as an argument, not read live inside the async think() task."""

    physio: physiology.PhysiologyState
    park: frozen_head_state_park.FrozenHeadStatePark
    start_hour: float
    true_pos: tuple[float, float]
    believed_pos: tuple[float, float]
    last_ate_min_ago: float
    rng_state: str


class LoopState:
    """The tick-by-tick simulation state — everything advance_tick() needs and mutates.
    Deliberately separate from RunnerLoop (which is about the brain/decision side): this is
    just the physical/environmental side, and keeping it as its own object is what lets
    build_initial_state/restore_state/advance_tick be tested directly with a scripted list of
    Decisions, with no asyncio, no DB, and no LLM call — see tests/test_resume.py and ADR-0009.
    """

    def __init__(
        self,
        physio: physiology.PhysiologyState,
        park: frozen_head_state_park.FrozenHeadStatePark,
        start_hour: float,
        true_pos: tuple[float, float],
        believed_pos: tuple[float, float],
        last_ate_min_ago: float,
        rng: random.Random,
    ):
        self.physio = physio
        self.park = park
        self.start_hour = start_hour
        self.true_pos = true_pos
        self.believed_pos = believed_pos
        self.last_ate_min_ago = last_ate_min_ago
        self.rng = rng


@lru_cache(maxsize=1)
def _start_coords() -> tuple[float, float]:
    """The start point never changes — cached because the GPX file is ~178k lines and
    gpxpy.parse() takes >1s to fully parse it just to read the first point. Pre-existing
    cost, not introduced here; it only became visible once build_initial_state() (and its
    tests) started calling this more than once per process."""
    with GPX_PATH.open() as f:
        gpx = gpxpy.parse(f)
    point = gpx.tracks[0].segments[0].points[0]
    return (point.latitude, point.longitude)


def build_initial_state(rng: random.Random, start_hour: float) -> LoopState:
    """Fresh-start LoopState — no checkpoint exists yet for this runner."""
    physio = physiology.initial_state()
    park = frozen_head_state_park.initial_state(start_hour=start_hour, rng=rng)
    # true_pos == believed_pos for now — no navigation noise until sim/course.py exists
    start_pos = _start_coords()
    return LoopState(
        physio=physio,
        park=park,
        start_hour=start_hour,
        true_pos=start_pos,
        believed_pos=start_pos,
        last_ate_min_ago=0.0,
        rng=rng,
    )


def restore_state(checkpoint: Checkpoint) -> LoopState:
    """ADR-0008's resume path: reconstruct a LoopState bit-exactly from a checkpoint, including
    rng — see db.rng_from_state's docstring for why a bare json round-trip isn't enough."""
    return LoopState(
        physio=checkpoint.physiology,
        park=checkpoint.environment,
        start_hour=checkpoint.start_hour,
        true_pos=checkpoint.true_pos,
        believed_pos=checkpoint.believed_pos,
        last_ate_min_ago=checkpoint.last_ate_min_ago,
        rng=db.rng_from_state(checkpoint.rng_state),
    )


def advance_tick(state: LoopState, decision: Decision, dt_min: float) -> Observation:
    """Advance LoopState by one tick under `decision` (the runner's currently-executing
    decision — CLAUDE.md: the sim never waits for the brain, it keeps running the last one).
    Mutates `state` in place and returns the resulting Observation.

    physio.tick() reads state.park.heat_index BEFORE state.park is advanced this tick —
    matches the original inline loop body exactly; physiology sees last tick's environment,
    not this tick's, and changing that ordering would silently change every physiology value
    from here on."""
    state.physio = physiology.tick(
        state.physio,
        BASE_HR,
        decision.effort,
        state.park.heat_index,
        dt_min,
        ate=decision.eat,
        drank=decision.drink,
    )
    state.park = frozen_head_state_park.tick(state.park, dt_min, state.start_hour, state.rng)
    state.last_ate_min_ago = 0.0 if decision.eat else state.last_ate_min_ago + dt_min
    return _build_observation(
        state.physio,
        state.park,
        state.start_hour,
        decision,
        state.believed_pos,
        state.last_ate_min_ago,
    )


def _estimate_cadence(effort_rpe: int) -> int:
    """No biomechanics model yet — a cosmetic placeholder tying cadence loosely to effort."""
    return 150 + effort_rpe * 3


async def _compact_and_checkpoint(
    runner: RunnerLoop, obs: Observation, decision: Decision, snapshot: StateSnapshot
) -> None:
    """ADR-0008: after a successful decision, fold any aged-out turns into the running
    summary and write a checkpoint. Failures here are swallowed by think()'s own try/except —
    losing a checkpoint write shouldn't crash the tick loop any more than a DB hiccup should."""
    all_turns = await db.get_all_turns(runner.conn, runner.runner_id)
    new_summary, remaining = compact_if_needed(runner.summary, all_turns, n=SLIDING_WINDOW_N)
    if new_summary != runner.summary:
        folded_count = len(all_turns) - len(remaining)
        runner.summary_covers_up_to_elapsed_min = round(all_turns[folded_count - 1][0].elapsed_min)
        print(f"[{obs.clock_time}] ...{runner.runner_id}'s memory compacts: {new_summary!r}")
    runner.summary = new_summary

    checkpoint = Checkpoint(
        runner_id=runner.runner_id,
        elapsed_min=snapshot.physio.elapsed_min,
        physiology=snapshot.physio,
        environment=snapshot.park,
        start_hour=snapshot.start_hour,
        true_pos=snapshot.true_pos,
        believed_pos=snapshot.believed_pos,
        loop=STUB_LOOP,
        books_found=STUB_BOOKS_FOUND,
        last_ate_min_ago=snapshot.last_ate_min_ago,
        last_decision=decision,
        rng_state=snapshot.rng_state,
        summary_text=runner.summary,
        summary_covers_up_to_elapsed_min=runner.summary_covers_up_to_elapsed_min,
    )
    await db.save_checkpoint(runner.conn, checkpoint)


async def think(runner: RunnerLoop, obs: Observation, snapshot: StateSnapshot) -> None:
    """obs/snapshot are passed as arguments (not closed over) so each task sees the state from
    the tick that created it, not whatever the loop variables happen to be by the time this
    runs — Python's closures are late-binding, and the loop reassigns them every tick.

    Wrapped in a bare except, not just relying on Participant.decide()'s own try/except:
    CLAUDE.md's "no retries, keep the old decision, log a funny line" contract is about the
    whole think() task, not just the brain call — a DB hiccup here shouldn't be able to
    propagate through the un-awaited asyncio.create_task() and crash the entire race loop at
    the final asyncio.gather().
    """
    try:
        history = await db.get_recent_turns(runner.conn, runner.runner_id, SLIDING_WINDOW_N)
        with propagate_attributes(session_id=runner.runner_id, tags=["barkley-smoke-test"]):
            async with runner.sem:
                outcome = await runner.participant.decide(obs, history, runner.summary)
        await db.log_turn(
            runner.conn, runner.runner_id, obs, outcome.decision, outcome.failure_reason
        )
        if outcome.decision is not None:
            await _compact_and_checkpoint(runner, obs, outcome.decision, snapshot)
    except Exception as e:
        # Distinct from Participant.decide()'s own try/except above: this catches failures in
        # think() itself (a DB hiccup in get_recent_turns/log_turn, etc.), which decide()'s
        # BrainOutcome can't have captured a reason for. Best-effort persisted too — a "the
        # sim never waits for the LLM" hiccup still deserves a durable record, not just print().
        reason = f"{type(e).__name__}: {e}"
        print(f"[{obs.clock_time}] ...{runner.runner_id} mumbles incoherently... ({reason})")
        try:
            await db.log_turn(runner.conn, runner.runner_id, obs, None, reason)
        except Exception:
            pass  # persisting the failure failing too shouldn't crash the tick loop either
        return
    if outcome.decision is None:
        print(f"[{obs.clock_time}] ...{runner.runner_id} mumbles incoherently...")
        return
    print(f"[{obs.clock_time}] {runner.runner_id}: {outcome.decision.monologue!r}")
    runner.decision = outcome.decision


def _build_observation(
    physio: physiology.PhysiologyState,
    park: frozen_head_state_park.FrozenHeadStatePark,
    start_hour: float,
    decision: Decision,
    believed_pos: tuple[float, float],
    last_ate_min_ago: float,
) -> Observation:
    collapsed = physiology.has_collapsed(physio.bonk_push_min)
    pace = physiology.compute_pace(
        BASE_PACE_MIN_PER_KM, decision.effort, physio.glycogen_pct, collapsed
    )
    return Observation(
        elapsed_min=round(physio.elapsed_min),
        clock_time=format_clock_time(start_hour, physio.elapsed_min),
        hr=physio.hr,
        pace_min_per_km=pace,
        cadence=_estimate_cadence(decision.effort),
        feel=physiology.describe_feel(physio.glycogen_pct, collapsed),
        last_ate_min_ago=round(last_ate_min_ago),
        bearing_deg=decision.bearing_deg,
        gps_guess=believed_pos,
        terrain=STUB_TERRAIN,
        weather=park.weather,
        books_found=STUB_BOOKS_FOUND,
        loop=STUB_LOOP,
        hallucination=None,
    )


async def run() -> None:
    conn = await db.init_db(DB_PATH)
    runner = RunnerLoop(Participant(load_persona(PERSONA_PATH)), conn, asyncio.Semaphore(5))

    checkpoint = await db.load_checkpoint(conn, runner.runner_id)
    if checkpoint is not None:
        state = restore_state(checkpoint)
        runner.decision = checkpoint.last_decision
        runner.summary = checkpoint.summary_text
        runner.summary_covers_up_to_elapsed_min = checkpoint.summary_covers_up_to_elapsed_min
        print(
            f"Resuming {runner.runner_id} from checkpoint at elapsed_min="
            f"{checkpoint.elapsed_min:.1f} (summary: {len(checkpoint.summary_text)} chars)"
        )
    else:
        rng = random.Random()
        start_hour = rng.uniform(0.0, 12.0)  # Barkley's horn blows any time midnight-noon
        state = build_initial_state(rng, start_hour)
        print(f"Starting {runner.runner_id} fresh, start_hour={start_hour:.2f}")

    tasks: list[asyncio.Task] = []
    n_ticks = int(TOTAL_SIM_MINUTES / TICK_DT_MIN)
    for _ in range(n_ticks):
        decision = runner.decision
        obs = advance_tick(state, decision, TICK_DT_MIN)
        # rng_state captured here, same tick as physio/park, so a checkpoint built from this
        # snapshot represents one consistent instant — not whatever rng looks like by the time
        # the async think() task using it actually runs.
        snapshot = StateSnapshot(
            physio=state.physio,
            park=state.park,
            start_hour=state.start_hour,
            true_pos=state.true_pos,
            believed_pos=state.believed_pos,
            last_ate_min_ago=state.last_ate_min_ago,
            rng_state=db.serialize_rng_state(state.rng),
        )
        print(f"[{obs.clock_time}] HR={obs.hr} pace={obs.pace_min_per_km:.1f} feel={obs.feel}")
        tasks.append(asyncio.create_task(think(runner, obs, snapshot)))
        await asyncio.sleep(TICK_DT_MIN * 60)

    await asyncio.gather(*tasks)
    await conn.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--fresh",
        action="store_true",
        help="Delete any existing smoke-test DB first, so this run starts a new race instead "
        "of resuming a checkpoint from a previous run (dev convenience — resuming-if-present "
        "is the correct behavior otherwise, see ADR-0008/ADR-0009).",
    )
    args = parser.parse_args()
    if args.fresh:
        Path(DB_PATH).unlink(missing_ok=True)

    asyncio.run(run())
