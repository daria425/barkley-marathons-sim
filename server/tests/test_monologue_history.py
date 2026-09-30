"""GET /monologues/{persona_name} (ADR-0021): the feed's backfill source. Bounded per request
(hard page cap), keyset-paginated, and safe to call before any run has created the DB.

Driven through FastAPI's TestClient against a temp DB seeded via db.log_turn; async db calls use
asyncio.run() like the other tests (no pytest-asyncio in this project).
"""

import asyncio

import pytest
from fastapi.testclient import TestClient

import db
import main
from models import Decision, Observation

RUNNER = "Hank"


def _decision(text: str) -> Decision:
    return Decision(
        effort=5,
        eat=False,
        drink=False,
        bearing_deg=0.0,
        rest_min=0,
        quit=False,
        monologue=text,
    )


def _obs(elapsed_min: float) -> Observation:
    return Observation(
        elapsed_min=int(elapsed_min),
        clock_time="Day 1, 6:00 AM",
        hr=80,
        pace_min_per_km=12.0,
        cadence=160,
        feel="feeling good",
        last_ate_min_ago=0,
        bearing_deg=0.0,
        gps_guess=(36.1, -84.7),
        dist_to_trail_km=0.0,
        terrain="gravel road, gentle climb",
        weather="clear",
        books_found=0,
        loop=1,
        hallucination=None,
        event=None,
    )


def _seed(path: str, n: int, runner: str = RUNNER, failed_at: int | None = None) -> None:
    async def go():
        conn = await db.init_db(path)
        for i in range(n):
            decision = None if i == failed_at else _decision(f"thought {i}")
            reason = "boom" if decision is None else None
            await db.log_turn(conn, runner, 36.1, -84.7, _obs(i * 0.5), decision, reason)
        await conn.commit()
        await conn.close()

    asyncio.run(go())


@pytest.fixture
def client(tmp_path, monkeypatch):
    path = str(tmp_path / "race.db")
    monkeypatch.setattr(main, "DB_PATH", path)
    return TestClient(main.app), path


def test_missing_db_returns_empty_page_and_creates_no_file(client, tmp_path):
    c, path = client
    body = c.get(f"/monologues/{RUNNER}").json()
    assert body == {"entries": [], "has_more": False}
    assert not (tmp_path / "race.db").exists()


def test_returns_latest_page_oldest_first_with_has_more(client):
    c, path = client
    _seed(path, 120)
    body = c.get(f"/monologues/{RUNNER}?limit=50").json()
    texts = [e["text"] for e in body["entries"]]
    assert texts == [f"thought {i}" for i in range(70, 120)]
    assert body["has_more"] is True


def test_before_cursor_pages_back_without_overlap_to_the_start(client):
    c, path = client
    _seed(path, 120)
    first = c.get(f"/monologues/{RUNNER}?limit=50").json()
    cursor = first["entries"][0]["id"]
    second = c.get(f"/monologues/{RUNNER}?limit=50&before={cursor}").json()
    cursor = second["entries"][0]["id"]
    third = c.get(f"/monologues/{RUNNER}?limit=50&before={cursor}").json()
    assert [e["text"] for e in second["entries"]] == [f"thought {i}" for i in range(20, 70)]
    assert second["has_more"] is True
    assert [e["text"] for e in third["entries"]] == [f"thought {i}" for i in range(0, 20)]
    assert third["has_more"] is False


def test_turns_sharing_a_rounded_minute_keep_insertion_order_and_survive_paging(client):
    """log_turn rounds elapsed_min to whole minutes, so ticks 0.5 apart tie on it — ordering and
    the cursor must come from the row id, or paging skips/reorders tied turns."""
    c, path = client
    _seed(path, 40)
    distinct = {e["elapsed_min"] for e in c.get(f"/monologues/{RUNNER}?limit=40").json()["entries"]}
    assert len(distinct) < 40  # the ties this test is about actually exist
    seen: list[str] = []
    cursor = None
    while True:
        url = f"/monologues/{RUNNER}?limit=7" + (f"&before={cursor}" if cursor else "")
        page = c.get(url).json()
        seen = [e["text"] for e in page["entries"]] + seen
        cursor = page["entries"][0]["id"]
        if not page["has_more"]:
            break
    assert seen == [f"thought {i}" for i in range(40)]


def test_limit_is_clamped_to_the_hard_page_cap(client):
    c, path = client
    _seed(path, main.MONOLOGUE_PAGE_MAX + 50)
    body = c.get(f"/monologues/{RUNNER}?limit=100000").json()
    assert len(body["entries"]) == main.MONOLOGUE_PAGE_MAX
    assert body["has_more"] is True


def test_failed_turns_and_other_runners_are_excluded(client):
    c, path = client
    _seed(path, 5, failed_at=2)
    _seed(path, 3, runner="Other")
    body = c.get(f"/monologues/{RUNNER}").json()
    texts = [e["text"] for e in body["entries"]]
    assert texts == ["thought 0", "thought 1", "thought 3", "thought 4"]


def test_rejects_nonpositive_limit(client):
    c, _ = client
    assert c.get(f"/monologues/{RUNNER}?limit=0").status_code == 422


def test_prompt_window_and_full_history_replay_in_insertion_order_despite_minute_ties(tmp_path):
    """Regression: turns were ordered by the rounded elapsed_min, so ties (two or more ticks per
    whole minute) came back scrambled in the window replayed to the LLM."""
    path = str(tmp_path / "race.db")
    _seed(path, 40)

    async def read():
        conn = await db.init_db(path)
        window = await db.get_recent_turns(conn, RUNNER, 20)
        everything = await db.get_all_turns(conn, RUNNER)
        await conn.close()
        return window, everything

    window, everything = asyncio.run(read())
    assert [d.monologue for _, d in window] == [f"thought {i}" for i in range(20, 40)]
    assert [d.monologue for _, d in everything] == [f"thought {i}" for i in range(40)]
