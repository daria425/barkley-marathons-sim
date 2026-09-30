import { useState } from "react";
import { useAppDispatch, useAppSelector } from "@/store/hooks";
import { Panel } from "@/components/Panel";
import { RaceOutcome } from "@/components/RaceOutcome";
import { Button } from "@/components/ui/button";
import type { RunnerState } from "@/types/models";
import { endStatus } from "@/lib/raceOutcome";
import { canLoadOlder, fromHistory, MAX_MONOLOGUES } from "@/lib/monologues";
import { fetchMonologuePage } from "@/lib/monologueApi";
import { monologueHistoryLatestLoaded, monologueHistoryOlderLoaded } from "@/store/raceSlice";

export function MonologueFeed({ personaName, runner }: {
  personaName: string;
  runner?: RunnerState;
}) {
  const dispatch = useAppDispatch();
  const entries = useAppSelector((state) => state.race.monologues[personaName] ?? []);
  const meta = useAppSelector((state) => state.race.monologueMeta[personaName]);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const reversed = entries.slice().reverse();
  const hasMore = meta?.hasMore ?? false;

  async function loadOlder() {
    if (loadingOlder) return;
    setLoadingOlder(true);
    setLoadFailed(false);
    try {
      // The oldest loaded entry's id is the cursor. A live-only store (the initial backfill
      // failed) has no ids yet, so this fetches the latest page instead.
      const before = entries[0]?.id;
      const page = await fetchMonologuePage(personaName, before);
      if (before === undefined) {
        dispatch(monologueHistoryLatestLoaded({
          personaName,
          entries: fromHistory(page),
          hasMore: page.has_more,
          sinceSeq: meta?.liveSeq ?? 0,
        }));
      } else {
        dispatch(monologueHistoryOlderLoaded({
          personaName,
          entries: fromHistory(page),
          hasMore: page.has_more,
        }));
      }
    } catch {
      setLoadFailed(true);
    } finally {
      setLoadingOlder(false);
    }
  }

  return (
    <Panel className="flex min-h-0 flex-1 flex-col p-4">
      <div className="-mr-2 flex-1 space-y-3 overflow-y-auto pr-2">
        {runner && <RaceOutcome runner={runner} />}
        <h3 className="mb-3 text-sm font-semibold tracking-wide">Monologue</h3>
        {reversed.length === 0 && !endStatus(runner) && (
          <p className="text-sm text-muted-foreground">Waiting on the runner's first thought…</p>
        )}
        {reversed.map((entry, i) => (
          <p key={entry.id ?? `live-${entry.seq}-${i}`} className="text-sm leading-relaxed text-foreground/90">
            <span className="mr-1.5 font-mono text-xs text-primary tabular-nums">
              {entry.elapsedMin}m
            </span>
            {entry.text}
          </p>
        ))}
        {canLoadOlder(entries, hasMore) && (
          <Button variant="outline" size="sm" className="w-full" onClick={loadOlder} disabled={loadingOlder}>
            {loadingOlder ? "Loading…" : loadFailed ? "Couldn't load — retry" : "Load older"}
          </Button>
        )}
        {hasMore && entries.length >= MAX_MONOLOGUES && (
          <p className="text-center text-xs text-muted-foreground">
            Showing the latest {MAX_MONOLOGUES} entries.
          </p>
        )}
      </div>
    </Panel>
  );
}
