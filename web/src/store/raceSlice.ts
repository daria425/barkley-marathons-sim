import { createSlice, type PayloadAction } from "@reduxjs/toolkit";
import type { FrozenHeadStatePark, RaceState, RunnerState } from "../types/models";

export interface MonologueEntry {
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
}

const initialState: RaceSliceState = {
  elapsedMin: 0,
  environment: null,
  runners: {},
  monologues: {},
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
          (state.monologues[name] ??= []).push({
            elapsedMin: next.elapsed_min,
            text: nextMonologue,
          });
        }
      }
      state.runners = next.runners;
    },
  },
});

export const { raceStateReceived } = raceSlice.actions;
export default raceSlice.reducer;
