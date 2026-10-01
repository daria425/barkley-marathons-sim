# ADR-0022: Operator kill switch — `POST /stop` ends the run as a plain `dnf_cutoff`

**Date**: 2026-10-01
**Status**: accepted
**Deciders**: Daria

## Context

A full run is 60 hours of per-tick LLM calls (~$80). There was no way to stop one: if it went
wrong at hour 5 (a bug, a bad persona turn, an outage-induced mess) the only options were letting
it keep spending or killing the Fly machine — which leaves a `running` checkpoint that the next
`POST /run` would happily resume and keep spending on. `run()` is a background task created by
`main.py`, so stopping it needs a signal threaded into the tick loop.

## Decision

1. `POST /stop` (admin-token gated, like `/run`) sets a per-run `asyncio.Event` that
   `_supervised_run` passes to `run(stop_event=...)`.
2. `run()` treats it as one more race-end condition via `_check_race_end(..., killed=True)`: the
   next tick finalizes through the existing ADR-0019 path as **`dnf_cutoff`** (final checkpoint
   written, terminal state broadcast once, loop exits). A real `finished`/`dnf_quit` on the same
   tick still wins. The tick sleep is interruptible (`sleep_unless_stopped`), so this takes
   effect within the current tick, not up to 30s later; in-flight brain calls are cancelled so
   nothing more is paid for. The supervisor's crash-backoff sleep is interruptible too.
3. **Viewers are deliberately not told.** There is no new status and nothing new on `/status`:
   the frontend's existing `dnf_cutoff` copy ("completed only N/5 loops in 60 hours") and the
   public state read like a normal finish. The only trace is a `[kill switch]` warning in the
   server log and the admin-only response of `/stop`.
4. If the graceful path hasn't finished within `STOP_GRACE_SEC` (10s) the task is hard-cancelled
   and `/stop` reports `force-cancelled`.

## Alternatives Considered

### Alternative 1: `task.cancel()` on the run task

- **Pros**: no change to `run()`.
- **Cons**: no terminal checkpoint or broadcast — viewers see a runner frozen as "running"
  forever, and a later `/run` resumes it and spends again.
- **Why not**: kept only as the timeout fallback.

### Alternative 2: A dedicated `dnf_stopped` status

- **Pros**: honest in the data and the UI.
- **Cons**: a wire-model change, new frontend states and copy.
- **Why not**: explicitly declined — this is a dev utility, and the goal is for an aborted run to
  look like it ended on schedule.

## Consequences

### Positive

- A bad run can be stopped immediately and can't be resumed into more spend: the ended checkpoint
  makes any later `POST /run` just re-announce the outcome.

### Negative

- A killed run reads as a real DNF in the DB (`checkpoints.status = dnf_cutoff`) — nothing in the
  data distinguishes it afterward except the log line. Starting a new race needs the DB wiped.
- The watch face still shows the true elapsed time (say 5h), which is the one thing that doesn't
  match "60 hours".

### Risks

- The hard-cancel fallback leaves the last checkpoint at `running` and no terminal broadcast; a
  later `POST /run` would resume it. Wipe the DB after a `force-cancelled`.
