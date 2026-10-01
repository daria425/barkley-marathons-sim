# ADR-0023: Hourly race monitor via GitHub Actions and an admin health endpoint

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: Daria

## Context

A full run is 60 hours at ~$80, unattended. The failure that matters most is quiet: a failed brain
call never crashes the sim (CLAUDE.md: keep the old decision, log "mumbles"), so a dead API key or
exhausted credit just makes the runner repeat its last decision for hours while the sim ticks on.
Langfuse can't show this on its own (invalid-JSON/schema failures aren't API errors), and `/status`
only reports liveness. An LLM-driven poller (a `/loop` in a session, or a cloud routine) needs
the laptop awake for 60h or secrets handed to a remote agent, for what is a mostly mechanical check.

## Decision

1. `GET /admin/health` (admin-token gated, not in the OpenAPI schema): read-only aggregates over
   the prod DB — failed brain calls in the last hour and in a row, age of the newest logged turn,
   and the checkpoint's race status (`db.get_health_summary`).
2. `server/scripts/monitor_race.py` (stdlib only) combines `/status`, `/admin/health` and the last
   hour of Langfuse (error-level observations, average prompt size, cache-read tokens) through a
   pure `evaluate()`. It exits non-zero on a problem and stays quiet — exit 0 — when there is no
   active race (not started, finished, or any `dnf_*`).
3. `.github/workflows/race-monitor.yml` runs it hourly (and on demand). A failed job is the alert:
   GitHub emails the repo owner. No phone push. It is alert-only and never calls `POST /stop`.

## Alternatives Considered

### Alternative 1: `/loop 1h` or a cloud routine running Claude

- **Pros**: could reason about odd failures and has repo context.
- **Cons**: a session must stay alive 60h, or a remote agent holds the Langfuse keys and admin
  token; every hourly check spends tokens on a mechanical comparison.
- **Why not**: the checks are thresholds; triage can happen on demand when an alert fires.

### Alternative 2: Read the DB over `fly ssh` from CI

- **Pros**: no new endpoint.
- **Cons**: a Fly token as a CI secret, `flyctl` in the workflow, shell-quoted SQL.
- **Why not**: one authenticated `GET` is simpler and narrower.

### Alternative 3: Auto-stop on anomaly

- **Pros**: caps spend without a human.
- **Cons**: a false positive kills a healthy 60h race.
- **Why not**: alert-only; the kill switch (ADR-0022) stays a human decision.

## Consequences

### Positive

- A quiet outage (dead key, empty credit, stalled loop, caching regression, prompt-size blowup)
  surfaces within about an hour, from the same checks every time.

### Negative

- Hourly granularity, and GitHub may delay scheduled runs by several minutes. Failing the job is
  email-only by default (a user whose notification settings exclude workflow failures gets nothing).
- The repo needs four Actions secrets (`RACE_ADMIN_TOKEN` and the three Langfuse values).

### Risks

- The cache-read check keys off Langfuse usage field names (`input_cached_tokens` and variants);
  no non-zero value has been observed yet, so confirm it fires correctly on the real run.
- Langfuse being unreachable is logged but deliberately not an alert; only the backend being
  unreachable (or the race itself looking unhealthy) fails the job.
