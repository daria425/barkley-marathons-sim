"""Minimal SQLite logging for the smoke-test vertical slice (ADR-0005).

Deliberately a throwaway schema — one flat table, raw JSON blobs — just to prove
Observation/Decision pairs get logged end to end. Phase 2 ("Memory and persistence" in
CLAUDE.md) designs the real checkpoint/resume schema; don't build on this one.

runner_id is stored now even though v1 has exactly one runner, so multi-persona later is a
WHERE clause, not a schema change (same reasoning as the concurrency semaphore in loop.py).
"""

import json
import random

import aiosqlite

from models import Checkpoint, Decision, Observation

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runner_id TEXT NOT NULL,
    elapsed_min REAL NOT NULL,
    observation_json TEXT NOT NULL,
    decision_json TEXT,
    failure_reason TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

# ADR-0008's real checkpoint/resume schema — separate from `turns` above (which stays the
# throwaway append-only log). One row per runner, replaced wholesale on every brain decision.
CREATE_CHECKPOINTS_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS checkpoints (
    runner_id TEXT PRIMARY KEY,
    checkpoint_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

# TO DO pool connections when we have multiple runners if needed


async def init_db(path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path)
    await conn.execute(CREATE_TABLE_SQL)
    await conn.execute(CREATE_CHECKPOINTS_TABLE_SQL)
    await conn.commit()
    return conn


def serialize_rng_state(rng: random.Random) -> str:
    """random.getstate() returns (version, internal_state, gauss_next), where internal_state
    is a 625-tuple of ints. A bare json.dumps/loads round-trip turns tuples into lists, and
    random.setstate() requires the internal_state to be an actual tuple — passing it a list
    raises. This helper (and deserialize_rng_state below) does the tuple<->list conversion
    explicitly so callers never hit that silently-wrong-shape bug."""
    return json.dumps(rng.getstate())


def deserialize_rng_state(state_json: str) -> tuple:
    version, internal_state, gauss_next = json.loads(state_json)
    return (version, tuple(internal_state), gauss_next)


def rng_from_state(state_json: str) -> random.Random:
    rng = random.Random()
    rng.setstate(deserialize_rng_state(state_json))
    return rng


async def log_turn(
    conn: aiosqlite.Connection,
    runner_id: str,
    obs: Observation,
    decision: Decision | None,
    failure_reason: str | None = None,
) -> None:
    """decision may be None — a failed brain call still gets logged (with a null decision) so
    the smoke test shows how often parsing/API failures happen, not just successes.

    failure_reason persists WHY (e.g. "RuntimeError: simulated API outage") — for us, never
    shown to the LLM (get_recent_turns/get_all_turns only ever select decision_json IS NOT
    NULL rows). Before this, the only record of a failure was a print() line, gone the moment
    the process exited.

    elapsed_min is rounded to the nearest whole minute before storage — memory.py replays
    this back to the LLM, and "about 4 minutes in" reads more like how a runner actually
    thinks than a 0.25-precision float would.
    """
    await conn.execute(
        "INSERT INTO turns (runner_id, elapsed_min, observation_json, decision_json, "
        "failure_reason) VALUES (?, ?, ?, ?, ?)",
        (
            runner_id,
            round(obs.elapsed_min),
            obs.model_dump_json(),
            decision.model_dump_json() if decision else None,
            failure_reason,
        ),
    )
    await conn.commit()


async def get_recent_turns(
    conn: aiosqlite.Connection, runner_id: str, limit: int
) -> list[tuple[Observation, Decision]]:
    """The last `limit` turns for this runner that actually produced a Decision, oldest
    first (ready to replay in prompt order). Turns with a null decision (failed brain calls)
    are skipped — there's nothing to replay as the assistant's prior turn."""
    cursor = await conn.execute(
        "SELECT observation_json, decision_json FROM turns "
        "WHERE runner_id = ? AND decision_json IS NOT NULL "
        "ORDER BY elapsed_min DESC LIMIT ?",
        (runner_id, limit),
    )
    rows = await cursor.fetchall()
    return [
        (Observation.model_validate_json(obs_json), Decision.model_validate_json(dec_json))
        for obs_json, dec_json in reversed(rows)
    ]


async def count_turns(conn: aiosqlite.Connection, runner_id: str) -> int:
    cursor = await conn.execute(
        "SELECT COUNT(*) FROM turns WHERE runner_id = ? AND decision_json IS NOT NULL",
        (runner_id,),
    )
    (count,) = await cursor.fetchone()
    return count


async def get_all_turns(
    conn: aiosqlite.Connection, runner_id: str
) -> list[tuple[Observation, Decision]]:
    """The FULL turn history for this runner, oldest-first, no LIMIT — unlike
    get_recent_turns, this is what agents/memory.py's compact_if_needed (ADR-0008) needs to
    find the turns that have aged out of the last-N window."""
    cursor = await conn.execute(
        "SELECT observation_json, decision_json FROM turns "
        "WHERE runner_id = ? AND decision_json IS NOT NULL ORDER BY elapsed_min ASC",
        (runner_id,),
    )
    rows = await cursor.fetchall()
    return [
        (Observation.model_validate_json(obs_json), Decision.model_validate_json(dec_json))
        for obs_json, dec_json in rows
    ]


async def get_failures(
    conn: aiosqlite.Connection, runner_id: str, limit: int = 50
) -> list[tuple[int, str | None]]:
    """(elapsed_min, failure_reason) for every failed turn, most recent first — for us to
    actually look at ("how often and why is this breaking"), not for prompt replay. A row can
    have failure_reason=None if it failed before ADR-0008's diagnostic existed, or if
    think()'s outer except couldn't determine a reason."""
    cursor = await conn.execute(
        "SELECT elapsed_min, failure_reason FROM turns "
        "WHERE runner_id = ? AND decision_json IS NULL "
        "ORDER BY elapsed_min DESC LIMIT ?",
        (runner_id, limit),
    )
    return await cursor.fetchall()


async def save_checkpoint(conn: aiosqlite.Connection, checkpoint: Checkpoint) -> None:
    """Upsert — ADR-0008's checkpoint is one row per runner_id, replaced wholesale on every
    brain decision, not appended like `turns`."""
    await conn.execute(
        "INSERT INTO checkpoints (runner_id, checkpoint_json, updated_at) "
        "VALUES (?, ?, datetime('now')) "
        "ON CONFLICT(runner_id) DO UPDATE SET "
        "checkpoint_json = excluded.checkpoint_json, updated_at = excluded.updated_at",
        (checkpoint.runner_id, checkpoint.model_dump_json()),
    )
    await conn.commit()


async def load_checkpoint(conn: aiosqlite.Connection, runner_id: str) -> Checkpoint | None:
    """None means no checkpoint exists yet for this runner — a fresh start, not a resume."""
    cursor = await conn.execute(
        "SELECT checkpoint_json FROM checkpoints WHERE runner_id = ?", (runner_id,)
    )
    row = await cursor.fetchone()
    return Checkpoint.model_validate_json(row[0]) if row else None
