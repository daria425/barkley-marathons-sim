"""Hourly health check for a live race (ADR-0023), run by .github/workflows/race-monitor.yml.

Exits non-zero (failing the GitHub Actions job, which emails the repo owner) when something needs
a human; exits 0 and stays quiet when there is no active race or everything looks healthy. Alert
only — it never calls POST /stop.

Stdlib only so CI needs no install step. The judgement lives in the pure `evaluate()`; the rest
is fetching. Usage: `python -m scripts.monitor_race` from server/, configured via env:
API_BASE, RACE_ADMIN_TOKEN, and (optional) LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY /
LANGFUSE_BASE_URL.
"""

import base64
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime, timedelta

# no brain decision logged at all for this long while the race is 'running' => loop is dead.
# (a failed brain call still logs a turn, so this only trips when ticks stop entirely)
STALL_SEC = 300
FAILURES_PER_HOUR_LIMIT = 3
CONSECUTIVE_FAILURES_LIMIT = 3
# per-call prompt size ceiling; the expected end-of-race size is ~50k (ADR-0018/0020)
MAX_AVG_PROMPT_TOKENS = 80_000
# the summary clears any plausible minimum cacheable prefix well before this; see ADR-0020
CACHE_EXPECTED_AFTER_MIN = 1200.0
_CACHE_READ_KEYS = ("input_cached_tokens", "cache_read_input_tokens", "input_cache_read")
_PROMPT_KEYS = ("input", *_CACHE_READ_KEYS, "input_cache_creation", "cache_creation_input_tokens")


def evaluate(status: dict, health: dict, langfuse: dict | None) -> list[str]:
    """Returns the list of problems (empty = healthy). `status` is GET /status, `health` is GET
    /admin/health, `langfuse` is summarize_observations() output or None if Langfuse couldn't
    be queried (that alone is not an alert — a flaky third party shouldn't wake anyone)."""
    if health.get("race_status") != "running":
        return []  # not started, or already over (finished / dnf_*) — nothing to watch

    problems = []
    age = health.get("latest_turn_age_sec")
    if age is None or age > STALL_SEC:
        problems.append(
            f"race is 'running' but no turn was logged for {age}s — the loop looks dead"
        )
    elif status.get("running") is False:
        problems.append("race is 'running' but the server reports its run task is not alive")

    failures = health.get("failures_last_hour", 0)
    consecutive = health.get("consecutive_failures", 0)
    if failures >= FAILURES_PER_HOUR_LIMIT or consecutive >= CONSECUTIVE_FAILURES_LIMIT:
        reasons = "; ".join(
            f"{r['count']}x {r['reason']}" for r in health.get("recent_failure_reasons", [])
        )
        problems.append(
            f"brain calls failing: {failures} in the last hour, {consecutive} in a row"
            + (f" ({reasons})" if reasons else "")
        )

    if langfuse is not None:
        problems += _langfuse_problems(langfuse, health.get("race_elapsed_min") or 0.0)
    return problems


def _langfuse_problems(lf: dict, elapsed_min: float) -> list[str]:
    problems = []
    if lf["errors"]:
        problems.append(
            f"Langfuse shows {lf['errors']} ERROR-level observation(s) in the last hour"
        )
    if lf["generations"] and lf["avg_prompt_tokens"] > MAX_AVG_PROMPT_TOKENS:
        problems.append(
            f"average prompt is {lf['avg_prompt_tokens']:.0f} tokens/call "
            f"(limit {MAX_AVG_PROMPT_TOKENS}) — memory growth or a cost blowup"
        )
    if lf["generations"] and elapsed_min >= CACHE_EXPECTED_AFTER_MIN and lf["cache_read"] == 0:
        problems.append(
            f"no prompt-cache reads in {lf['generations']} calls at {elapsed_min:.0f} sim-min — "
            "caching has stopped working (ADR-0020)"
        )
    return problems


def summarize_observations(observations: list[dict]) -> dict:
    """Collapses Langfuse observations (usage fields included) into the numbers evaluate() and
    the job summary use."""
    gens = [o for o in observations if o.get("type") == "GENERATION"]
    prompt_total = cache_read = 0
    for o in gens:
        usage = o.get("usageDetails") or {}
        prompt_total += sum(usage.get(k, 0) or 0 for k in _PROMPT_KEYS)
        cache_read += sum(usage.get(k, 0) or 0 for k in _CACHE_READ_KEYS)
    return {
        "generations": len(gens),
        "errors": sum(1 for o in observations if o.get("level") == "ERROR"),
        "avg_prompt_tokens": prompt_total / len(gens) if gens else 0.0,
        "cache_read": cache_read,
    }


def _get_json(url: str, headers: dict[str, str], attempts: int = 2) -> dict:
    last: Exception | None = None
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=20) as resp:
                return json.load(resp)
        except Exception as e:  # noqa: BLE001 — retried once, then surfaced to the caller
            last = e
            if attempt + 1 < attempts:
                time.sleep(5)
    raise RuntimeError(f"GET {url.split('?')[0]} failed: {last}")


def fetch_langfuse(now: datetime) -> dict | None:
    pk, sk = os.environ.get("LANGFUSE_PUBLIC_KEY"), os.environ.get("LANGFUSE_SECRET_KEY")
    base = os.environ.get("LANGFUSE_BASE_URL")
    if not (pk and sk and base):
        print("langfuse: not configured, skipping", file=sys.stderr)
        return None
    auth = base64.b64encode(f"{pk}:{sk}".encode()).decode()
    observations: list[dict] = []
    cursor = None
    try:
        while len(observations) < 1000:
            params = {
                "fromStartTime": (now - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "toStartTime": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "fields": "core,basic,usage",
                "limit": "200",
            }
            if cursor:
                params["cursor"] = cursor
            body = _get_json(
                f"{base.rstrip('/')}/api/public/v2/observations?{urllib.parse.urlencode(params)}",
                {"Authorization": f"Basic {auth}"},
            )
            observations += body.get("data", [])
            cursor = (body.get("meta") or {}).get("cursor")
            if not cursor:
                break
    except RuntimeError as e:
        print(f"langfuse: unavailable, skipping ({e})", file=sys.stderr)
        return None
    return summarize_observations(observations)


def _write_step_summary(health: dict, lf: dict | None, problems: list[str]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    rows = {
        "race status": health.get("race_status"),
        "sim elapsed (min)": health.get("race_elapsed_min"),
        "turns last hour": health.get("turns_last_hour"),
        "failed brain calls last hour": health.get("failures_last_hour"),
        "consecutive failures": health.get("consecutive_failures"),
        "latest turn age (s)": health.get("latest_turn_age_sec"),
    }
    if lf is not None:
        rows |= {
            "langfuse generations": lf["generations"],
            "langfuse errors": lf["errors"],
            "avg prompt tokens": round(lf["avg_prompt_tokens"]),
            "cache-read tokens": lf["cache_read"],
        }
    lines = ["## Race monitor", "", "| metric | value |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in rows.items()]
    lines += (
        ["", *(f"- :x: {p}" for p in problems)] if problems else ["", ":white_check_mark: healthy"]
    )
    with open(path, "a") as f:
        f.write("\n".join(lines) + "\n")


def main() -> int:
    base = os.environ.get("API_BASE", "https://barkley-marathons-simulator.fly.dev").rstrip("/")
    token = os.environ.get("RACE_ADMIN_TOKEN", "")
    try:
        status = _get_json(f"{base}/status", {})
        health = _get_json(f"{base}/admin/health", {"x-admin-token": token})
    except RuntimeError as e:
        print(f"::error::race backend unreachable: {e}")
        return 1
    now = datetime.now(UTC)
    lf = fetch_langfuse(now) if health.get("race_status") == "running" else None
    problems = evaluate(status, health, lf)
    _write_step_summary(health, lf, problems)
    if health.get("race_status") != "running":
        print(f"no active race (status: {health.get('race_status')}) — nothing to check")
    for p in problems:
        print(f"::error::{p}")
    print("healthy" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
