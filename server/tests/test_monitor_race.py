"""The hourly race monitor (ADR-0023): evaluate() is pure, so each failure mode is pinned with
canned /status, /admin/health and Langfuse data; /admin/health itself is checked against a seeded
tmp DB (reusing test_monologue_history's seeding helpers).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient
from test_db import make_checkpoint
from test_monologue_history import RUNNER, _decision, _obs

import db
import main
from scripts.monitor_race import (
    CACHE_EXPECTED_AFTER_MIN,
    evaluate,
    summarize_observations,
)

HEALTHY_STATUS = {"running": True}


def _health(**overrides):
    base = {
        "race_status": "running",
        "race_elapsed_min": 300.0,
        "turns_last_hour": 120,
        "failures_last_hour": 0,
        "consecutive_failures": 0,
        "latest_turn_age_sec": 20,
        "recent_failure_reasons": [],
    }
    return base | overrides


def _lf(**overrides):
    return {"generations": 120, "errors": 0, "avg_prompt_tokens": 20_000.0, "cache_read": 10} | (
        overrides
    )


def test_healthy_race_has_no_problems():
    assert evaluate(HEALTHY_STATUS, _health(), _lf()) == []


@pytest.mark.parametrize("status", [None, "finished", "dnf_cutoff", "dnf_quit"])
def test_no_active_race_is_never_an_alert(status):
    dead = _health(race_status=status, latest_turn_age_sec=99_999, failures_last_hour=50)
    assert evaluate({"running": False}, dead, _lf(errors=9)) == []


def test_stalled_loop_is_reported():
    problems = evaluate(HEALTHY_STATUS, _health(latest_turn_age_sec=900), None)
    assert len(problems) == 1 and "loop looks dead" in problems[0]
    assert evaluate(HEALTHY_STATUS, _health(latest_turn_age_sec=None), None)


def test_dead_run_task_is_reported_even_if_a_turn_is_recent():
    problems = evaluate({"running": False}, _health(), None)
    assert len(problems) == 1 and "not alive" in problems[0]


def test_brain_call_failures_are_reported_with_reasons():
    health = _health(
        failures_last_hour=40,
        consecutive_failures=40,
        recent_failure_reasons=[{"reason": "AuthenticationError: invalid x-api-key", "count": 40}],
    )
    (problem,) = evaluate(HEALTHY_STATUS, health, None)
    assert "40 in the last hour" in problem and "AuthenticationError" in problem


def test_a_couple_of_scattered_failures_are_tolerated():
    assert (
        evaluate(HEALTHY_STATUS, _health(failures_last_hour=2, consecutive_failures=1), None) == []
    )


def test_langfuse_problems_errors_prompt_growth_and_missing_cache():
    assert any("ERROR-level" in p for p in evaluate(HEALTHY_STATUS, _health(), _lf(errors=2)))
    big = _lf(avg_prompt_tokens=120_000.0)
    assert any("tokens/call" in p for p in evaluate(HEALTHY_STATUS, _health(), big))
    late = _health(race_elapsed_min=CACHE_EXPECTED_AFTER_MIN + 1)
    assert any("caching" in p for p in evaluate(HEALTHY_STATUS, late, _lf(cache_read=0)))
    # early in the race there's legitimately nothing cacheable yet
    assert evaluate(HEALTHY_STATUS, _health(race_elapsed_min=60.0), _lf(cache_read=0)) == []


def test_unreachable_langfuse_alone_is_not_an_alert():
    assert evaluate(HEALTHY_STATUS, _health(), None) == []


def test_summarize_observations_counts_prompt_cache_and_errors():
    obs = [
        {
            "type": "GENERATION",
            "level": "DEFAULT",
            "usageDetails": {"input": 5000, "input_cached_tokens": 9000, "input_cache_creation": 0},
        },
        {
            "type": "GENERATION",
            "level": "ERROR",
            "usageDetails": {"input": 6000, "input_cached_tokens": 0, "input_cache_creation": 1000},
        },
        {"type": "SPAN", "level": "DEFAULT"},
    ]
    s = summarize_observations(obs)
    assert s["generations"] == 2 and s["errors"] == 1 and s["cache_read"] == 9000
    assert s["avg_prompt_tokens"] == (14_000 + 7_000) / 2
    assert summarize_observations([])["avg_prompt_tokens"] == 0.0


def _seed_turns(path: str, outcomes: list[bool], hours_old: dict[int, int] | None = None):
    """outcomes[i] True = a successful decision, False = a failed brain call."""

    async def go():
        conn = await db.init_db(path)
        for i, ok in enumerate(outcomes):
            await db.log_turn(
                conn,
                RUNNER,
                36.1,
                -84.7,
                _obs(i * 0.5),
                _decision(f"t{i}") if ok else None,
                None if ok else "AuthenticationError: invalid x-api-key",
            )
        for row_id, hours in (hours_old or {}).items():
            await conn.execute(
                "UPDATE turns SET created_at = datetime('now', ?) WHERE id = ?",
                (f"-{hours} hours", row_id),
            )
        await conn.commit()
        await conn.close()

    asyncio.run(go())


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "race.db")
    monkeypatch.setattr(main, "DB_PATH", path)
    monkeypatch.setattr(main, "RACE_ADMIN_TOKEN", "secret")
    return TestClient(main.app), path


def test_admin_health_requires_the_admin_token_and_is_not_in_the_schema(client):
    c, _ = client
    assert c.get("/admin/health").status_code == 401
    assert c.get("/admin/health", headers={"x-admin-token": "wrong"}).status_code == 401
    assert "/admin/health" not in c.get("/openapi.json").json()["paths"]


def test_admin_health_before_any_run_reports_no_race_and_creates_no_file(client, tmp_path):
    c, _ = client
    body = c.get("/admin/health", headers={"x-admin-token": "secret"}).json()
    assert body == {"race_status": None}
    assert not (tmp_path / "race.db").exists()


def test_admin_health_counts_failures_and_staleness(client):
    c, path = client
    # 3 ok, then 4 failed in a row; the first 2 rows are 3 hours old (outside the last hour)
    _seed_turns(path, [True, True, True, False, False, False, False], hours_old={1: 3, 2: 3, 4: 3})
    body = c.get("/admin/health", headers={"x-admin-token": "secret"}).json()
    assert body["turns_total"] == 7
    assert body["failures_total"] == 4
    assert body["turns_last_hour"] == 4  # ids 3, 5, 6, 7
    assert body["failures_last_hour"] == 3  # ids 5, 6, 7 (id 4 is 3h old)
    assert body["consecutive_failures"] == 4
    assert body["latest_turn_age_sec"] < 60
    assert body["recent_failure_reasons"] == [
        {"reason": "AuthenticationError: invalid x-api-key", "count": 3}
    ]
    # no checkpoint row yet -> no race status; the monitor treats that as "nothing to watch"
    assert body["race_status"] is None


@pytest.mark.parametrize("status", ["running", "dnf_cutoff", "finished"])
def test_admin_health_reports_the_checkpoint_race_status(client, status):
    c, path = client

    async def go():
        conn = await db.init_db(path)
        checkpoint = make_checkpoint(runner_id=RUNNER).model_copy(update={"status": status})
        await db.save_checkpoint(conn, checkpoint)
        await conn.close()

    asyncio.run(go())
    body = c.get("/admin/health", headers={"x-admin-token": "secret"}).json()
    assert body["race_status"] == status
