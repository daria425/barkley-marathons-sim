"""Vertical-slice smoke test loop (ADR-0005) — proves Observation -> Decision -> monologue
works end to end before sim/course.py exists for real.

Course-dependent Observation fields (position, terrain, books, bearing) are hardcoded stubs
here, not read from a real course — see ADR-0005. Everything else (physiology, weather,
memory, logging) is the real thing.
"""

import asyncio
import random
from pathlib import Path

import aiosqlite
import gpxpy
from langfuse import propagate_attributes

import db
from agents.memory import SLIDING_WINDOW_N
from agents.participant import Participant
from agents.personas import load_persona
from models import Decision, Observation
from sim import frozen_head_state_park, physiology
from sim.sim_utils import format_clock_time

TICK_DT_MIN = 0.25  # ADR-0005: finer than CLAUDE.md's "1 tick = 1 sim-minute", smoke-test only
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


def _start_coords() -> tuple[float, float]:
    with GPX_PATH.open() as f:
        gpx = gpxpy.parse(f)
    point = gpx.tracks[0].segments[0].points[0]
    return (point.latitude, point.longitude)


def _estimate_cadence(effort_rpe: int) -> int:
    """No biomechanics model yet — a cosmetic placeholder tying cadence loosely to effort."""
    return 150 + effort_rpe * 3


async def think(runner: RunnerLoop, obs: Observation) -> None:
    """obs is passed as an argument (not closed over) so each task sees the Observation from
    the tick that created it, not whatever `obs` happens to be by the time this runs —
    Python's closures are late-binding, and the loop reassigns `obs` every tick.

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
                decision = await runner.participant.decide(obs, history)
        await db.log_turn(runner.conn, runner.runner_id, obs, decision)
    except Exception:
        print(f"[{obs.clock_time}] ...{runner.runner_id} mumbles incoherently...")
        return
    if decision is None:
        print(f"[{obs.clock_time}] ...{runner.runner_id} mumbles incoherently...")
        return
    print(f"[{obs.clock_time}] {runner.runner_id}: {decision.monologue!r}")
    runner.decision = decision


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
    rng = random.Random()
    start_hour = rng.uniform(0.0, 12.0)  # Barkley's horn blows any time midnight-noon

    conn = await db.init_db(DB_PATH)
    runner = RunnerLoop(Participant(load_persona(PERSONA_PATH)), conn, asyncio.Semaphore(5))

    physio = physiology.initial_state()
    park = frozen_head_state_park.initial_state(start_hour=start_hour, rng=rng)
    # true_pos == believed_pos for now — no navigation noise until sim/course.py exists
    believed_pos = _start_coords()
    last_ate_min_ago = 0.0

    tasks: list[asyncio.Task] = []
    n_ticks = int(TOTAL_SIM_MINUTES / TICK_DT_MIN)
    for _ in range(n_ticks):
        decision = runner.decision
        physio = physiology.tick(
            physio,
            BASE_HR,
            decision.effort,
            park.heat_index,
            TICK_DT_MIN,
            ate=decision.eat,
            drank=decision.drink,
        )
        park = frozen_head_state_park.tick(park, TICK_DT_MIN, start_hour, rng)
        last_ate_min_ago = 0.0 if decision.eat else last_ate_min_ago + TICK_DT_MIN

        obs = _build_observation(physio, park, start_hour, decision, believed_pos, last_ate_min_ago)
        print(f"[{obs.clock_time}] HR={obs.hr} pace={obs.pace_min_per_km:.1f} feel={obs.feel}")
        tasks.append(asyncio.create_task(think(runner, obs)))
        await asyncio.sleep(TICK_DT_MIN * 60)

    await asyncio.gather(*tasks)
    await conn.close()


if __name__ == "__main__":
    asyncio.run(run())
