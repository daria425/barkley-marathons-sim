"""Minimal SQLite logging for the smoke-test vertical slice (ADR-0005).

Deliberately a throwaway schema — one flat table, raw JSON blobs — just to prove
Observation/Decision pairs get logged end to end. Phase 2 ("Memory and persistence" in
CLAUDE.md) designs the real checkpoint/resume schema; don't build on this one.

runner_id is stored now even though v1 has exactly one runner, so multi-persona later is a
WHERE clause, not a schema change (same reasoning as the concurrency semaphore in loop.py).
"""

import aiosqlite

from models import Decision, Observation

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS turns (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    runner_id TEXT NOT NULL,
    elapsed_min REAL NOT NULL,
    observation_json TEXT NOT NULL,
    decision_json TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
)
"""

# TO DO pool connections when we have multiple runners if needed


async def init_db(path: str) -> aiosqlite.Connection:
    conn = await aiosqlite.connect(path)
    await conn.execute(CREATE_TABLE_SQL)
    await conn.commit()
    return conn


async def log_turn(
    conn: aiosqlite.Connection, runner_id: str, obs: Observation, decision: Decision | None
) -> None:
    """decision may be None — a failed brain call still gets logged (with a null decision)
    so the smoke test shows how often parsing/API failures happen, not just successes.

    elapsed_min is rounded to the nearest whole minute before storage — memory.py replays
    this back to the LLM, and "about 4 minutes in" reads more like how a runner actually
    thinks than a 0.25-precision float would.
    """
    await conn.execute(
        "INSERT INTO turns (runner_id, elapsed_min, observation_json, decision_json) "
        "VALUES (?, ?, ?, ?)",
        (
            runner_id,
            round(obs.elapsed_min),
            obs.model_dump_json(),
            decision.model_dump_json() if decision else None,
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
