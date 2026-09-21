import type { RunnerState } from "../types/models";

function formatElapsed(min: number): string {
  const h = Math.floor(min / 60);
  const m = Math.round(min % 60);
  return `${h}h ${m}m`;
}

export function WatchFace({ runner }: { runner: RunnerState }) {
  const { physiology } = runner;
  return (
    <div className="watch-face">
      <h3>{runner.persona_name}</h3>
      <dl>
        <dt>Elapsed</dt>
        <dd>{formatElapsed(physiology.elapsed_min)}</dd>
        <dt>HR</dt>
        <dd>{physiology.hr} bpm</dd>
        <dt>Pace</dt>
        <dd>{runner.pace_min_per_km.toFixed(1)} min/km</dd>
        <dt>Glycogen</dt>
        <dd>{physiology.glycogen_pct.toFixed(0)}%</dd>
        <dt>Hydration</dt>
        <dd>{physiology.hydration_pct.toFixed(0)}%</dd>
        <dt>Feel</dt>
        <dd>{runner.feel}</dd>
        <dt>Loop</dt>
        <dd>
          {runner.loop} ({runner.books_found} books)
        </dd>
      </dl>
    </div>
  );
}
