"""Vertical-slice smoke test loop (ADR-0005) — proves Observation -> Decision -> monologue
works end to end. Course/books/navigation (sim/course.py, ADR-0010) is the real thing now;
everything else (physiology, weather, memory, logging) already was.
"""

import asyncio
import random
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

import aiosqlite
from langfuse import propagate_attributes

import db
from agents.memory import COMPACT_BATCH_SIZE, SLIDING_WINDOW_N, compact_if_needed
from agents.participant import Participant
from agents.personas import load_persona
from models import Checkpoint, Decision, Observation, RaceState, RunnerState
from sim import course as course_mod
from sim import frozen_head_state_park, physiology
from sim.sim_utils import format_clock_time

# Called once per tick with the current RaceState, and again (with an updated RunnerState
# after a fresh Decision) whenever a brain call lands — main.py wires this to its WS
# broadcaster. None (the default) keeps the CLI/smoke-test/test_resume.py path unaffected.
OnUpdate = Callable[[RaceState], Awaitable[None]]

# Every tick spawns a brain call, deliberately not gated by trigger events (ADR-0015) — trigger
# moments like book-found are surfaced via Observation.event instead of call scheduling. Real
# wall-clock time between ticks is TICK_DT_MIN * 60s (at speed=1).
TICK_DT_MIN = 0.25

# Race length in sim-minutes. Real target per CLAUDE.md ("60-hour cutoff"). run()'s
# duration_min param defaults to this — pass a smaller value (e.g. via
# scripts/smoke_test.py --duration-min) for a short smoke test or a bounded live canary
# instead of editing this constant.
FULL_RACE_MINUTES = 60 * 60
DB_PATH = "smoke_test.db"
PERSONA_PATH = Path(__file__).parent.parent / "agents" / "personas" / "barkley_expert.yaml"

BASE_HR = 60
BASE_PACE_MIN_PER_KM = 10.0  # untuned placeholder, see ADR-0004's tuning note

STARTING_DECISION = Decision(
    effort=5,
    eat=False,
    drink=False,
    bearing_deg=0.0,
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
        # fresh-start case; run() overwrites all three from the checkpoint when resuming.
        self.summary = ""
        self.summary_covers_up_to_elapsed_min = 0
        # High-water mark for batched compaction (memory.py's compact_if_needed) — how many of
        # this runner's turns are already folded into `summary`.
        self.summary_folded_count = 0


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
    loop: int
    books_collected: frozenset[int]
    dist_since_loop_start_km: float
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
        loop: int = 1,
        books_collected: frozenset[int] = frozenset(),
        dist_since_loop_start_km: float = 0.0,
    ):
        self.physio = physio
        self.park = park
        self.start_hour = start_hour
        self.true_pos = true_pos
        self.believed_pos = believed_pos
        self.last_ate_min_ago = last_ate_min_ago
        self.rng = rng
        self.loop = loop
        self.books_collected = books_collected
        self.dist_since_loop_start_km = dist_since_loop_start_km


def build_initial_state(rng: random.Random, start_hour: float) -> LoopState:
    """Fresh-start LoopState — no checkpoint exists yet for this runner."""
    physio = physiology.initial_state()
    park = frozen_head_state_park.initial_state(start_hour=start_hour, rng=rng)
    start_pos = course_mod.start_coords(course_mod.load_course())
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
        loop=checkpoint.loop,
        books_collected=frozenset(checkpoint.books_collected_this_loop),
        dist_since_loop_start_km=checkpoint.dist_since_loop_start_km,
    )


def advance_tick(state: LoopState, decision: Decision, dt_min: float) -> Observation:
    """Advance LoopState by one tick under `decision` (the runner's currently-executing
    decision — CLAUDE.md: the sim never waits for the brain, it keeps running the last one).
    Mutates `state` in place and returns the resulting Observation.

    physio.tick() reads state.park.heat_index BEFORE state.park is advanced this tick —
    matches the original inline loop body exactly; physiology sees last tick's environment,
    not this tick's, and changing that ordering would silently change every physiology value
    from here on. Grade is read at state.true_pos before this tick's move, same reasoning."""
    the_course = course_mod.load_course()
    grade_pct = course_mod.grade_pct_at(the_course, state.true_pos)

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

    collapsed = physiology.has_collapsed(state.physio.bonk_push_min)
    pace = physiology.compute_pace(
        BASE_PACE_MIN_PER_KM, decision.effort, state.physio.glycogen_pct, collapsed, grade_pct
    )
    # A tick under a rest_min>0 decision covers no ground — otherwise "rest" was free (HR/
    # glycogen/position all advanced exactly as if still moving), so the sim had no way to make
    # resting cost anything, and no way for a repeated rest decision to ever change what the
    # next Observation looks like. `pace` above still reflects effort, unchanged — it's what
    # you'd be running at if you weren't resting, not what ground you actually covered.
    distance_km = 0.0 if decision.rest_min > 0 else dt_min / pace
    state.true_pos = course_mod.advance_position(state.true_pos, decision.bearing_deg, distance_km)
    state.dist_since_loop_start_km += distance_km
    if course_mod.loop_completed(the_course, state.true_pos, state.dist_since_loop_start_km):
        state.loop += 1
        state.dist_since_loop_start_km = 0.0
        state.books_collected = frozenset()
    state.books_collected, has_found_new_book = course_mod.books_found_this_tick(
        the_course, state.true_pos, state.books_collected
    )
    state.believed_pos = course_mod.believed_position(
        state.true_pos,
        state.park.fog_pct,
        state.park.is_daylight,
        state.physio.elapsed_min,
        state.rng,
    )

    return _build_observation(
        the_course,
        state.physio,
        state.park,
        state.start_hour,
        decision,
        state.true_pos,
        state.believed_pos,
        state.loop,
        state.books_collected,
        state.last_ate_min_ago,
        pace,
        has_found_new_book,
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
    new_summary, remaining, new_folded_count = compact_if_needed(
        runner.summary,
        all_turns,
        runner.summary_folded_count,
        n=SLIDING_WINDOW_N,
        batch_size=COMPACT_BATCH_SIZE,
    )
    if new_summary != runner.summary:
        newly_folded_elapsed = all_turns[new_folded_count - 1][0].elapsed_min
        runner.summary_covers_up_to_elapsed_min = round(newly_folded_elapsed)
        print(f"[{obs.clock_time}] ...{runner.runner_id}'s memory compacts: {new_summary!r}")
    runner.summary = new_summary
    runner.summary_folded_count = new_folded_count

    checkpoint = Checkpoint(
        runner_id=runner.runner_id,
        elapsed_min=snapshot.physio.elapsed_min,
        physiology=snapshot.physio,
        environment=snapshot.park,
        start_hour=snapshot.start_hour,
        true_pos=snapshot.true_pos,
        believed_pos=snapshot.believed_pos,
        loop=snapshot.loop,
        books_found=len(snapshot.books_collected),
        books_collected_this_loop=sorted(snapshot.books_collected),
        dist_since_loop_start_km=snapshot.dist_since_loop_start_km,
        last_ate_min_ago=snapshot.last_ate_min_ago,
        last_decision=decision,
        rng_state=snapshot.rng_state,
        summary_text=runner.summary,
        summary_covers_up_to_elapsed_min=runner.summary_covers_up_to_elapsed_min,
        summary_folded_count=runner.summary_folded_count,
    )
    await db.save_checkpoint(runner.conn, checkpoint)


async def think(
    runner: RunnerLoop, obs: Observation, snapshot: StateSnapshot, on_update: OnUpdate | None = None
) -> None:
    """obs/snapshot are passed as arguments (not closed over) so each task sees the state from
    the tick that created it, not whatever the loop variables happen to be by the time this
    runs — Python's closures are late-binding, and the loop reassigns them every tick.

    Wrapped in a bare except, not just relying on Participant.decide()'s own try/except:
    CLAUDE.md's "no retries, keep the old decision, log a funny line" contract is about the
    whole think() task, not just the brain call — a DB hiccup here shouldn't be able to
    propagate through the un-awaited asyncio.create_task() and crash the entire race loop at
    the final asyncio.gather().
    """
    true_lat = snapshot.true_pos[0]
    true_lon = snapshot.true_pos[1]
    try:
        history = await db.get_recent_turns(runner.conn, runner.runner_id, SLIDING_WINDOW_N)
        with propagate_attributes(session_id=runner.runner_id, tags=["barkley-smoke-test"]):
            async with runner.sem:
                outcome = await runner.participant.decide(obs, history, runner.summary)
        await db.log_turn(
            runner.conn,
            runner.runner_id,
            true_lat,
            true_lon,
            obs,
            outcome.decision,
            outcome.failure_reason,
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
            await db.log_turn(runner.conn, runner.runner_id, true_lat, true_lon, obs, None, reason)
        except Exception:
            pass  # persisting the failure failing too shouldn't crash the tick loop either
        return
    if outcome.decision is None:
        print(f"[{obs.clock_time}] ...{runner.runner_id} mumbles incoherently...")
        return
    print(f"[{obs.clock_time}] {runner.runner_id}: {outcome.decision.monologue!r}")
    runner.decision = outcome.decision
    if on_update is not None:
        runner_state = _build_runner_state(runner, obs, snapshot, outcome.decision)
        await on_update(_build_race_state(runner_state, snapshot))


def _build_runner_state(
    runner: RunnerLoop, obs: Observation, snapshot: StateSnapshot, decision: Decision
) -> RunnerState:
    return RunnerState(
        persona_name=runner.participant.persona.name,
        bib_number=runner.participant.persona.bib_number,
        physiology=snapshot.physio,
        true_pos=snapshot.true_pos,
        current_terrain=obs.terrain,
        believed_pos=snapshot.believed_pos,
        loop=snapshot.loop,
        books_found=len(snapshot.books_collected),
        pace_min_per_km=obs.pace_min_per_km,
        feel=obs.feel,
        last_decision=decision,
        last_event=obs.event,
    )


def _build_race_state(runner_state: RunnerState, snapshot: StateSnapshot) -> RaceState:
    # v1 is single-runner (CLAUDE.md), so a one-entry dict — multi-persona (phase 3) just
    # means the caller merges more runners' states into the same broadcast.
    return RaceState(
        elapsed_min=snapshot.physio.elapsed_min,
        environment=snapshot.park,
        runners={runner_state.persona_name: runner_state},
    )


def _build_observation(
    course: course_mod.Course,
    physio: physiology.PhysiologyState,
    park: frozen_head_state_park.FrozenHeadStatePark,
    start_hour: float,
    decision: Decision,
    true_pos: tuple[float, float],
    believed_pos: tuple[float, float],
    loop: int,
    books_collected: frozenset[int],
    last_ate_min_ago: float,
    pace: float,
    has_found_new_book: bool,
) -> Observation:
    collapsed = physiology.has_collapsed(physio.bonk_push_min)
    event = None
    if has_found_new_book:
        event = "found_book"
    # do something else for other events IF we add them
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
        dist_to_trail_km=course_mod.dist_to_trail_km(course, true_pos),
        terrain=course_mod.terrain_at(course, true_pos),
        weather=park.weather,
        books_found=len(books_collected),
        loop=loop,
        hallucination=None,
        event=event,
    )


async def run(
    speed: float = 1.0,
    duration_min: float = FULL_RACE_MINUTES,
    on_update: OnUpdate | None = None,
) -> None:
    """speed=1.0 is real Barkley pacing (CLAUDE.md: "the eventual real way to run this is at
    1x realtime... 60x/600x speed is for iterating during development, not the intended
    experience") — higher values only compress wall-clock time between ticks, never sim time
    itself (TICK_DT_MIN, physiology, everything else is unchanged).

    duration_min is how much sim-time to run before returning, independent of speed — default
    is the full 60h race; pass a smaller value for a smoke test or a bounded live canary
    without touching FULL_RACE_MINUTES.

    on_update, when given, is awaited once per tick with the current RaceState (main.py wires
    this to its WS broadcaster) and again whenever a brain call lands mid-tick (see think()).
    Default None keeps the CLI/smoke-test/test_resume.py path unaffected."""
    conn = await db.init_db(DB_PATH)
    runner = RunnerLoop(Participant(load_persona(PERSONA_PATH)), conn, asyncio.Semaphore(5))

    checkpoint = await db.load_checkpoint(conn, runner.runner_id)
    if checkpoint is not None:
        state = restore_state(checkpoint)
        runner.decision = checkpoint.last_decision
        runner.summary = checkpoint.summary_text
        runner.summary_covers_up_to_elapsed_min = checkpoint.summary_covers_up_to_elapsed_min
        runner.summary_folded_count = checkpoint.summary_folded_count
        print(
            f"Resuming {runner.runner_id} from checkpoint at elapsed_min="
            f"{checkpoint.elapsed_min:.1f} (summary: {len(checkpoint.summary_text)} chars)"
        )
    else:
        rng = random.Random()
        # Barkley's horn blows any time midnight-noon
        start_hour = rng.uniform(0.0, 12.0)
        state = build_initial_state(rng, start_hour)
        print(f"Starting {runner.runner_id} fresh, start_hour={start_hour:.2f}")

    tasks: list[asyncio.Task] = []
    n_ticks = int(duration_min / TICK_DT_MIN)
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
            loop=state.loop,
            books_collected=state.books_collected,
            dist_since_loop_start_km=state.dist_since_loop_start_km,
            last_ate_min_ago=state.last_ate_min_ago,
            rng_state=db.serialize_rng_state(state.rng),
        )
        print(f"[{obs.clock_time}] HR={obs.hr} pace={obs.pace_min_per_km:.1f} feel={obs.feel}")
        if on_update is not None:
            runner_state = _build_runner_state(runner, obs, snapshot, decision)
            await on_update(_build_race_state(runner_state, snapshot))
        tasks.append(asyncio.create_task(think(runner, obs, snapshot, on_update)))
        await asyncio.sleep(TICK_DT_MIN * 60 / speed)

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
    parser.add_argument(
        "--speed",
        type=float,
        default=1.0,
        help="Wall-clock speedup (e.g. 60 = 1 sim-minute every real second). Dev convenience "
        "only — sim time itself (TICK_DT_MIN, physiology) never changes; see CLAUDE.md's "
        "'Speed multiplier is a dev convenience, not the target mode.' Default 1.0 = real "
        "Barkley pacing.",
    )
    parser.add_argument(
        "--duration-min",
        type=float,
        default=FULL_RACE_MINUTES,
        help="Sim-minutes to run before stopping, independent of --speed. Default is the full "
        "60h race (3600). Pass a smaller value for a short smoke test or a bounded live canary.",
    )
    args = parser.parse_args()
    if args.fresh:
        Path(DB_PATH).unlink(missing_ok=True)

    asyncio.run(run(speed=args.speed, duration_min=args.duration_min))
