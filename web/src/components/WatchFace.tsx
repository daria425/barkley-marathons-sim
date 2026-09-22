import type { RunnerState } from "@/types/models";
import { Panel } from "@/components/Panel";
import { Badge } from "@/components/ui/badge";

function formatElapsed(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return `${h}h ${m}m`;
}

function Stat({ label, value, accent }: { label: string; value: string; accent?: boolean }) {
  return (
    <div className="flex flex-col gap-0.5">
      <dt className="text-[11px] font-medium tracking-wide text-muted-foreground uppercase">
        {label}
      </dt>
      <dd
        className={
          "font-mono text-xl leading-none tabular-nums " +
          (accent ? "text-primary" : "text-foreground")
        }
      >
        {value}
      </dd>
    </div>
  );
}

export function WatchFace({ runner }: { runner: RunnerState }) {
  const { physiology } = runner;

  return (
    <Panel className="p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold tracking-wide">{runner.persona_name}</h3>
        <Badge variant="outline" className="border-white/10 text-muted-foreground">
          Bib #{runner.bib_number}
        </Badge>
      </div>

      <dl className="grid grid-cols-2 gap-x-4 gap-y-3">
        <Stat label="Elapsed" value={formatElapsed(physiology.elapsed_min)} />
        <Stat label="HR" value={`${physiology.hr} bpm`} accent />
        <Stat label="Pace" value={`${runner.pace_min_per_km.toFixed(1)} /km`} />
        <Stat label="Glycogen" value={`${physiology.glycogen_pct.toFixed(0)}%`} />
        <Stat label="Hydration" value={`${physiology.hydration_pct.toFixed(0)}%`} />
        <Stat label="Loop" value={`${runner.loop} · ${runner.books_found} books`} />
      </dl>

      <p className="mt-3 border-t border-white/[0.06] pt-3 text-sm text-muted-foreground italic">
        {runner.feel}
      </p>
    </Panel>
  );
}
