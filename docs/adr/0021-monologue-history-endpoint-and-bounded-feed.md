# ADR-0021: Monologue history endpoint and a bounded feed

**Date**: 2026-09-30
**Status**: accepted
**Deciders**: Daria

## Context

The `/ws` stream only carries `RunnerState.last_decision`, and the frontend built its monologue
feed purely by accumulating those as they arrived. A client that connects late, refreshes, or
reconnects therefore sees one monologue — the end-state screen after a finished run showed only
the last message, and anyone opening the live 60h race mid-way would see a feed that starts when
they arrived. Fixing it means serving history, which raises a memory question on both ends: a
full race is ~7,200 monologues (~5-6MB of text) and the backend runs on a 512MB Fly machine that
has OOM'd before, while a browser tab can stay open for the whole race.

## Decision

1. `GET /monologues/{persona_name}?limit=&before=` returns `{entries, has_more}` (oldest-first)
   read from the `turns` table through a **read-only** SQLite connection (a request before any
   run exists returns an empty page instead of creating a DB file). Page size is **hard-capped
   at 200** server-side whatever the client asks for; the frontend asks for 50.
2. **Cursor and ordering are the row `id`, not `elapsed_min`.** `db.log_turn` rounds
   `elapsed_min` to whole minutes (by design, for the LLM's prompt), so several turns tie on it
   — as a cursor it would skip turns at page boundaries.
3. Frontend: on each socket (re)connect, per runner, fetch the latest page and merge it with
   live entries (`lib/monologues.ts`, dedupe by text — the live side stamps the tick a decision
   landed and the DB stamps the observation's minute, so elapsed time can't be the key). A
   "Load older" button pages backwards via the oldest loaded entry's id.
4. **The browser store is capped at 1,000 entries per runner**, enforced on live pushes, history
   merges, and "Load older" (which can never push past it; the button hides at the cap with a
   note). A tab left open for 60h can't accumulate 7,200 DOM nodes.

## Alternatives Considered

### Alternative 1: Send recent history in the WS on-connect message

- **Pros**: no new REST endpoint; no fetch race on connect.
- **Cons**: no way to page older; grows the WS contract (`RaceState`) for one panel; reconnects
  would resend it.
- **Why not**: "Load older" needs a request/response shape anyway.

### Alternative 2: Return the whole history

- **Pros**: simplest client.
- **Cons**: ~6MB per page load on a 512MB machine, unvirtualized rendering of thousands of nodes.
- **Why not**: unbounded by design; a traffic spike would be an OOM risk.

### Alternative 3: Virtualize the list instead of capping it

- **Pros**: could show the full transcript.
- **Cons**: a new dependency, and the store would still hold everything.
- **Why not**: deferred — the cap bounds memory outright; a full-transcript export is a separate
  feature if wanted.

## Consequences

### Positive

- Late joiners, refreshes, and reconnects all see the real feed; every request and the client
  store have a fixed memory ceiling.
- The new tests pin the tie-handling (`test_monologue_history.py`) and the merge/cap rules
  (`web/tests/monologues.test.mjs`).

### Negative

- A user can only scroll back 1,000 entries (about 8 hours of a 30s-tick race).
- Two identical monologue strings at the live/history seam would merge into one.

### Risks

- Events and hallucinations have the same late-joiner gap; nothing renders them yet, so left
  for when something does.
- Discovered while building this: `db.get_recent_turns` (and `get_all_turns`) still order by the
  rounded `elapsed_min`, so the sliding window replayed to the LLM is out of order within a
  minute. Tracked separately, not fixed here.
