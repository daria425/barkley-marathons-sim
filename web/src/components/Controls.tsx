import { Panel } from "@/components/Panel";
import { useAppSelector } from "@/store/hooks";
import type { ConnectionStatus } from "@/hooks/useRaceSocket";
import { cn } from "@/lib/utils";

function formatClock(elapsedMin: number): string {
  const totalMin = Math.floor(elapsedMin);
  const day = Math.floor(totalMin / 1440) + 1;
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  return `Day ${day}, ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const label =
    status === "open"
      ? "Live"
      : status === "connecting"
        ? "Connecting…"
        : "Disconnected";
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "open" &&
            "bg-primary shadow-[0_0_0_3px_rgba(0,174,199,0.25)]",
          status === "connecting" && "animate-pulse bg-secondary-foreground/60",
          status === "closed" && "bg-destructive",
        )}
      />
      {label}
    </div>
  );
}

/** The Command Center's bottom rail: brand mark, sim clock/weather, and connection status —
 * persistent chrome, not a modal (direction contract). The race is started from the backend
 * (POST /run), not from this UI — see CLAUDE.md's deployment notes. */
export function Controls({ status }: { status: ConnectionStatus }) {
  const elapsedMin = useAppSelector((state) => state.race.elapsedMin);
  const environment = useAppSelector((state) => state.race.environment);

  return (
    <Panel className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-3">
      <div className="flex items-center gap-4">
        <span className="text-sm font-bold tracking-[0.08em] text-foreground uppercase">
          Barkley Marathons <span className="text-primary">Simulator</span>
        </span>
        <div className="flex items-center gap-4 font-mono text-sm text-muted-foreground tabular-nums">
          <span className="text-foreground">{formatClock(elapsedMin)}</span>
          {environment && (
            <span className="hidden sm:inline">
              {environment.weather} · {environment.temperature_c.toFixed(0)}°C
              {environment.is_daylight ? "" : " · night"}
              {environment.fog_pct > 15 && environment.weather !== "fog"
                ? " · fog"
                : ""}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <ConnectionBadge status={status} />
      </div>
    </Panel>
  );
}
