import { useState } from "react";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAppSelector } from "@/store/hooks";
import type { ConnectionStatus } from "@/hooks/useRaceSocket";
import { cn } from "@/lib/utils";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;
const SPEEDS = [1, 60, 600] as const;

function formatClock(elapsedMin: number): string {
  const totalMin = Math.floor(elapsedMin);
  const day = Math.floor(totalMin / 1440) + 1;
  const h = Math.floor((totalMin % 1440) / 60);
  const m = totalMin % 60;
  return `Day ${day}, ${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}`;
}

function ConnectionBadge({ status }: { status: ConnectionStatus }) {
  const label =
    status === "open" ? "Live" : status === "connecting" ? "Connecting…" : "Disconnected";
  return (
    <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
      <span
        className={cn(
          "size-1.5 rounded-full",
          status === "open" && "bg-primary shadow-[0_0_0_3px_rgba(0,174,199,0.25)]",
          status === "connecting" && "animate-pulse bg-secondary-foreground/60",
          status === "closed" && "bg-destructive",
        )}
      />
      {label}
    </div>
  );
}

/** The Command Center's bottom rail: brand mark, sim clock/weather, speed control, and
 * start/connection status — persistent chrome, not a modal (direction contract). */
export function Controls({ status }: { status: ConnectionStatus }) {
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(60);
  const [starting, setStarting] = useState(false);
  const elapsedMin = useAppSelector((state) => state.race.elapsedMin);
  const environment = useAppSelector((state) => state.race.environment);

  async function handleStart() {
    setStarting(true);
    try {
      await fetch(`${API_BASE_URL}/run?speed=${speed}`, { method: "POST" });
    } finally {
      setStarting(false);
    }
  }

  return (
    <Panel className="flex flex-wrap items-center justify-between gap-x-6 gap-y-3 px-5 py-3">
      <div className="flex items-center gap-4">
        <span className="text-sm font-bold tracking-[0.08em] text-foreground uppercase">
          Barkley <span className="text-primary">Sim</span>
        </span>
        <div className="flex items-center gap-4 font-mono text-sm text-muted-foreground tabular-nums">
          <span className="text-foreground">{formatClock(elapsedMin)}</span>
          {environment && (
            <span className="hidden sm:inline">
              {environment.weather} · {environment.temperature_c.toFixed(0)}°C
              {environment.is_daylight ? "" : " · night"}
              {environment.fog_pct > 15 && environment.weather !== "fog" ? " · fog" : ""}
            </span>
          )}
        </div>
      </div>

      <div className="flex items-center gap-3">
        <ConnectionBadge status={status} />

        <Select
          value={String(speed)}
          onValueChange={(v) => setSpeed(Number(v) as typeof speed)}
        >
          <SelectTrigger size="sm" className="w-[84px] font-mono">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {SPEEDS.map((s) => (
              <SelectItem key={s} value={String(s)} className="font-mono">
                {s}x
              </SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Button onClick={handleStart} disabled={starting} size="sm">
          {starting ? "Starting…" : "Start"}
        </Button>
      </div>
    </Panel>
  );
}
