import type { RunnerState } from "@/types/models";

export type EndStatus = Exclude<RunnerState["status"], "running">;

export function endStatus(runner?: RunnerState): EndStatus | undefined {
  const status = runner?.status;
  return status === "finished" || status === "dnf_cutoff" || status === "dnf_quit"
    ? status : undefined;
}

export function completedLoops(runner: RunnerState): number {
  // The backend starts on loop 1 and increments after completing each loop.
  return Math.max(0, Math.min(5, runner.loop - 1));
}

export function formatElapsed(minutes: number): string {
  const total = Math.max(0, Math.floor(minutes));
  return `${Math.floor(total / 60)}h ${total % 60}m`;
}

export const OUTCOME_LABELS: Record<EndStatus, string> = {
  finished: "Finished",
  dnf_cutoff: "Time’s up",
  dnf_quit: "Called it a day",
};

export function outcomeMessage(runner: RunnerState): string | undefined {
  const name = runner.persona_name;
  const elapsed = formatElapsed(runner.physiology.elapsed_min);
  switch (endStatus(runner)) {
    case "finished":
      return `Race complete! ${name} finished 5 loops successfully in ${elapsed}.`;
    case "dnf_cutoff":
      return `Race complete! ${name} completed only ${completedLoops(runner)}/5 loops in 60 hours.`;
    case "dnf_quit":
      return `Race complete! ${name} did not finish the race and quit at ${elapsed}.`;
  }
}
