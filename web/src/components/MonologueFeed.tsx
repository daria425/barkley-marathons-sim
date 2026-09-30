import { useAppSelector } from "@/store/hooks";
import { Panel } from "@/components/Panel";
import { RaceOutcome } from "@/components/RaceOutcome";
import type { RunnerState } from "@/types/models";
import { endStatus } from "@/lib/raceOutcome";

export function MonologueFeed({ personaName, runner }: {
  personaName: string;
  runner?: RunnerState;
}) {
  const entries = useAppSelector((state) => state.race.monologues[personaName] ?? []);
  const reversed = entries.slice().reverse();

  return (
    <Panel className="flex min-h-0 flex-1 flex-col p-4">
      <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
        {runner && <RaceOutcome runner={runner} />}
        <h3 className="mb-3 text-sm font-semibold tracking-wide">Monologue</h3>
        {reversed.length === 0 && !endStatus(runner) && (
          <p className="text-sm text-muted-foreground">Waiting on the runner's first thought…</p>
        )}
        {reversed.map((entry, i) => (
          <p key={i} className="text-sm leading-relaxed text-foreground/90">
            <span className="mr-1.5 font-mono text-xs text-primary tabular-nums">
              {entry.elapsedMin}m
            </span>
            {entry.text}
          </p>
        ))}
      </div>
    </Panel>
  );
}
