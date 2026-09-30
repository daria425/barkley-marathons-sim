import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { FrozenHeadStatePark, RaceState, RunnerState } from "../types/models";
import {
  capNewest,
  MAX_MONOLOGUES,
  mergeLatest,
  mergeOlder,
  type MonologueEntry,
} from "../lib/monologues";

export type { MonologueEntry };

/** Per-runner feed bookkeeping that isn't the entries themselves (see lib/monologues.ts). */
interface MonologueMeta {
  /** more history exists on the server before the oldest loaded entry */
  hasMore: boolean;
  /** count of live entries pushed so far — the stamp for MonologueEntry.seq */
  liveSeq: number;
}

export interface EventEntry {
  elapsedMin: number;
  event: NonNullable<RunnerState["last_event"]>;
}

export interface HallucinationEntry {
  elapsedMin: number;
  text: string;
}

interface RaceSliceState {
  elapsedMin: number;
  environment: FrozenHeadStatePark | null;
  runners: Record<string, RunnerState>;
  // Keyed by persona_name, same as `runners` — separate from RaceState's own wire shape
  // since the backend only ever sends the latest last_decision, not a history of them.
  monologues: Record<string, MonologueEntry[]>;
  monologueMeta: Record<string, MonologueMeta>;
  // Same pattern as `monologues`, tracking RunnerState.last_event changes. Not rendered yet —
  // just made available to consumers (CLAUDE.md's event-emitter phase).
  events: Record<string, EventEntry[]>;
  // Same pattern again, tracking RunnerState.last_hallucination (ADR-0017). Not rendered yet.
  hallucinations: Record<string, HallucinationEntry[]>;
}

const initialState: RaceSliceState = {
  elapsedMin: 0,
  environment: null,
  runners: {},
  monologues: {},
  monologueMeta: {},
  events: {},
  hallucinations: {},
};

const raceSlice = createSlice({
  name: "race",
  initialState,
  reducers: {
    raceStateReceived(state, action: PayloadAction<RaceState>) {
      const next = action.payload;
      state.elapsedMin = next.elapsed_min;
      state.environment = next.environment;
      for (const [name, runner] of Object.entries(next.runners)) {
        const prevMonologue = state.runners[name]?.last_decision?.monologue;
        const nextMonologue = runner.last_decision?.monologue;
        if (nextMonologue && nextMonologue !== prevMonologue) {
          const meta = (state.monologueMeta[name] ??= { hasMore: true, liveSeq: 0 });
          meta.liveSeq += 1;
          const entries = (state.monologues[name] ??= []);
          entries.push({ elapsedMin: next.elapsed_min, text: nextMonologue, seq: meta.liveSeq });
          // A tab can stay open for the whole 60h race — never let the feed grow unbounded.
          if (entries.length > MAX_MONOLOGUES) state.monologues[name] = capNewest(entries);
        }
        const prevEvent = state.runners[name]?.last_event;
        const nextEvent = runner.last_event;
        if (nextEvent && nextEvent !== prevEvent) {
          (state.events[name] ??= []).push({
            elapsedMin: next.elapsed_min,
            event: nextEvent,
          });
        }
        const prevHallucination = state.runners[name]?.last_hallucination;
        const nextHallucination = runner.last_hallucination;
        if (nextHallucination && nextHallucination !== prevHallucination) {
          (state.hallucinations[name] ??= []).push({
            elapsedMin: next.elapsed_min,
            text: nextHallucination,
          });
        }
      }
      state.runners = next.runners;
    },
    /** Latest page of history (first load / reconnect backfill) — see mergeLatest. `sinceSeq` is
     * the runner's liveSeq when the request was issued. */
    monologueHistoryLatestLoaded(
      state,
      action: PayloadAction<{
        personaName: string;
        entries: MonologueEntry[];
        hasMore: boolean;
        sinceSeq: number;
      }>,
    ) {
      const { personaName, entries, hasMore, sinceSeq } = action.payload;
      const meta = (state.monologueMeta[personaName] ??= { hasMore: true, liveSeq: 0 });
      meta.hasMore = hasMore;
      state.monologues[personaName] = mergeLatest(
        state.monologues[personaName] ?? [],
        entries,
        sinceSeq,
      );
    },
    /** An older page from "Load older" — goes in front, never past the cap. */
    monologueHistoryOlderLoaded(
      state,
      action: PayloadAction<{ personaName: string; entries: MonologueEntry[]; hasMore: boolean }>,
    ) {
      const { personaName, entries, hasMore } = action.payload;
      const meta = (state.monologueMeta[personaName] ??= { hasMore: true, liveSeq: 0 });
      meta.hasMore = hasMore;
      state.monologues[personaName] = mergeOlder(state.monologues[personaName] ?? [], entries);
    },
  },
});

export const { raceStateReceived, monologueHistoryLatestLoaded, monologueHistoryOlderLoaded } =
  raceSlice.actions;
export default raceSlice.reducer;
