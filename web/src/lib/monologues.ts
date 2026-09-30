// Pure merge/cap logic for the monologue feed (ADR-0021). The /ws stream only carries the
// latest decision, so a client's feed is live entries (pushed as they arrive) stitched onto
// history fetched from GET /monologues/{persona}. Everything here is bounded on purpose: the
// store never holds more than MAX_MONOLOGUES per runner, however long a tab stays open or
// however many times "Load older" is pressed.

/** Hard ceiling on entries kept per runner (~0.8MB of text, ~1,000 DOM nodes). */
export const MAX_MONOLOGUES = 1000;
/** Entries per history request; the server clamps to its own, larger ceiling. */
export const PAGE_SIZE = 50;

export interface MonologueEntry {
  /** turns-table row id — only entries that came from history have one; it's the cursor for
   * paging older. Live entries (from the WS) don't. */
  id?: number;
  elapsedMin: number;
  text: string;
  /** Arrival counter for live entries only — lets a history merge tell "arrived after I
   * asked" from "already covered by the page". */
  seq?: number;
}

export interface HistoryPage {
  entries: { id: number; elapsed_min: number; text: string }[];
  has_more: boolean;
}

export function fromHistory(page: HistoryPage): MonologueEntry[] {
  return page.entries.map((e) => ({ id: e.id, elapsedMin: e.elapsed_min, text: e.text }));
}

/** Keeps the newest `max` entries. */
export function capNewest(entries: MonologueEntry[], max = MAX_MONOLOGUES): MonologueEntry[] {
  return entries.length > max ? entries.slice(entries.length - max) : entries;
}

/** Latest page from history (first load, or a reconnect backfill) onto whatever the store
 * already holds. History is the source of truth up to its newest entry; only live entries
 * NEWER than that survive:
 *  - if some existing entry matches the page, everything after the last match is newer;
 *  - if none match (empty store, or a long disconnect), keep only entries that arrived after
 *    the request was issued (`seq > sinceSeq`) — older ones are either covered by the page or
 *    a stale gap the page replaces. */
export function mergeLatest(
  existing: MonologueEntry[],
  incoming: MonologueEntry[],
  sinceSeq: number,
): MonologueEntry[] {
  const texts = new Set(incoming.map((e) => e.text));
  let lastMatch = -1;
  existing.forEach((e, i) => {
    if (texts.has(e.text)) lastMatch = i;
  });
  const newer = existing
    .slice(lastMatch + 1)
    .filter((e) => !texts.has(e.text) && (lastMatch >= 0 || (e.seq ?? 0) > sinceSeq));
  return capNewest([...incoming, ...newer]);
}

/** An older page (from "Load older") goes in front. Never pushes the store past the cap —
 * if it would, only the part of the page nearest the existing entries is kept. */
export function mergeOlder(
  existing: MonologueEntry[],
  incoming: MonologueEntry[],
): MonologueEntry[] {
  const texts = new Set(existing.map((e) => e.text));
  const fresh = incoming.filter((e) => !texts.has(e.text));
  const room = Math.max(0, MAX_MONOLOGUES - existing.length);
  return [...fresh.slice(Math.max(0, fresh.length - room)), ...existing];
}

/** Whether "Load older" should be offered: more exists on the server AND there's room. */
export function canLoadOlder(entries: MonologueEntry[], hasMore: boolean): boolean {
  return hasMore && entries.length < MAX_MONOLOGUES;
}
