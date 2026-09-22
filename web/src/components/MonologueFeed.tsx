import { useAppSelector } from "@/store/hooks";
import { Panel } from "@/components/Panel";

export function MonologueFeed({ personaName }: { personaName: string }) {
  const entries = useAppSelector((state) => state.race.monologues[personaName] ?? []);
  const reversed = entries.slice().reverse();

  return (
    <Panel className="flex min-h-0 flex-1 flex-col p-4">
      <h3 className="mb-3 text-sm font-semibold tracking-wide">Monologue</h3>
      <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
        {reversed.length === 0 && (
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
