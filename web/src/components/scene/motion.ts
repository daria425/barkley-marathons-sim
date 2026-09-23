import type { RunnerState } from "@/types/models";

/** Metres per second, with a visual ceiling. Rest decisions report a nonzero pace. */
export function runnerSpeed(runner?: RunnerState): number {
  const pace = runner?.pace_min_per_km;
  if (!runner || runner.last_decision?.rest_min || !pace || !Number.isFinite(pace) || pace < 0) return 0;
  return Math.min(5, 1000 / (60 * pace));
}

export interface SceneMotion {
  distance: number;
  phase: number;
  speed: number;
  time: number;
}
