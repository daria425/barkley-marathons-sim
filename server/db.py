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
    true_lat REAL NOT NULL,
    true_lon REAL NOT NULL,
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
    # WAL + busy_timeout: the sim holds this connection open for up to 60h straight, and a
    # future concurrent reader (an admin script, a status check) shouldn't be able to hit
    # "database is locked" against a writer that's still running.
    await conn.execute("PRAGMA journal_mode=WAL")
    await conn.execute("PRAGMA busy_timeout=5000")
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
    true_lat: float,
    true_lon: float,
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
        "INSERT INTO turns (runner_id, true_lat, true_lon, elapsed_min, observation_json, "
        "decision_json, failure_reason) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            runner_id,
            true_lat,
            true_lon,
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
    are skipped — there's nothing to replay as the assistant's prior turn.

    Ordered by row `id` (insertion order), NOT elapsed_min: log_turn rounds elapsed_min to whole
    minutes, so several turns tie on it, and ordering by it scrambled the window replayed to
    the LLM within each minute (ties come back in arbitrary order, and this query reverses)."""
    cursor = await conn.execute(
        "SELECT observation_json, decision_json FROM turns "
        "WHERE runner_id = ? AND decision_json IS NOT NULL "
        "ORDER BY id DESC LIMIT ?",
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


async def get_monologues_page(
    conn: aiosqlite.Connection, runner_id: str, limit: int, before: int | None = None
) -> tuple[list[tuple[int, float, str]], bool]:
    """One page of (id, elapsed_min, monologue) for the frontend feed, oldest-first, plus
    whether older rows exist past this page. Keyset-paginated and ordered on the row `id`
    (`before` is an exclusive id), NOT elapsed_min: log_turn rounds elapsed_min to whole
    minutes, so several turns share one value and it can neither order turns nor serve as a
    cursor without skipping rows at a page boundary. Uses json_extract so a page never parses
    whole Observation/Decision blobs in Python — memory per call is bounded by `limit`."""
    cursor = await conn.execute(
        "SELECT id, elapsed_min, json_extract(decision_json, '$.monologue') FROM turns "
        "WHERE runner_id = ? AND decision_json IS NOT NULL AND (? IS NULL OR id < ?) "
        "ORDER BY id DESC LIMIT ?",
        (runner_id, before, before, limit + 1),
    )
    rows = await cursor.fetchall()
    has_more = len(rows) > limit
    return [(i, elapsed, text) for i, elapsed, text in reversed(rows[:limit]) if text], has_more


async def get_health_summary(conn: aiosqlite.Connection) -> dict:
    """Aggregate run health for the hourly monitor (scripts/monitor_race.py, GET /admin/health):
    brain-call failure counts, how stale the newest logged turn is, and the checkpoint's race
    status. Read-only and cheap — a few aggregates over `turns` plus one tail scan — and a
    failed brain call is the thing that never crashes the sim (it just keeps the old decision),
    so this is the only place a quiet outage (dead API key, no credit) shows up in numbers."""
    cursor = await conn.execute(
        "SELECT count(*), "
        "coalesce(sum(decision_json IS NULL), 0), "
        "coalesce(sum(created_at >= datetime('now', '-1 hour')), 0), "
        "coalesce(sum(decision_json IS NULL AND created_at >= datetime('now', '-1 hour')), 0), "
        "cast(strftime('%s', 'now') - strftime('%s', max(created_at)) AS INTEGER), "
        "max(elapsed_min) FROM turns"
    )
    total, failures, turns_hour, failures_hour, age_sec, elapsed = await cursor.fetchone()

    cursor = await conn.execute("SELECT decision_json IS NULL FROM turns ORDER BY id DESC LIMIT 50")
    consecutive = 0
    for (failed,) in await cursor.fetchall():
        if not failed:
            break
        consecutive += 1

    cursor = await conn.execute(
        "SELECT substr(failure_reason, 1, 120), count(*) FROM turns "
        "WHERE decision_json IS NULL AND created_at >= datetime('now', '-1 hour') "
        "GROUP BY 1 ORDER BY 2 DESC LIMIT 3"
    )
    reasons = [{"reason": r or "unknown", "count": n} for r, n in await cursor.fetchall()]

    cursor = await conn.execute(
        "SELECT coalesce(json_extract(checkpoint_json, '$.status'), 'running') "
        "FROM checkpoints ORDER BY updated_at DESC LIMIT 1"
    )
    row = await cursor.fetchone()
    return {
        "race_status": row[0] if row else None,
        "race_elapsed_min": elapsed,
        "turns_total": total,
        "failures_total": failures,
        "turns_last_hour": turns_hour,
        "failures_last_hour": failures_hour,
        "consecutive_failures": consecutive,
        "latest_turn_age_sec": age_sec,
        "recent_failure_reasons": reasons,
    }


async def get_all_turns(
    conn: aiosqlite.Connection, runner_id: str
) -> list[tuple[Observation, Decision]]:
    """The FULL turn history for this runner, oldest-first, no LIMIT — unlike
    get_recent_turns, this is what agents/memory.py's compact_if_needed (ADR-0008) needs to
    find the turns that have aged out of the last-N window."""
    cursor = await conn.execute(
        "SELECT observation_json, decision_json FROM turns "
        "WHERE runner_id = ? AND decision_json IS NOT NULL ORDER BY id ASC",
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
        "ORDER BY id DESC LIMIT ?",
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
