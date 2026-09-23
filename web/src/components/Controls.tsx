import { useState } from "react";
import { Panel } from "@/components/Panel";
import { Button } from "@/components/ui/button";
import { useAppSelector } from "@/store/hooks";
import type { ConnectionStatus } from "@/hooks/useRaceSocket";
import { cn } from "@/lib/utils";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

// speed/duration_min are dev-iteration knobs (sim/loop.py's run()), not end-user controls —
// no UI for them, change these constants directly and redeploy. Currently set to a bounded
// live-API canary (75 sim-min ≈ 300 ticks) to ground-truth real token/cost numbers before
// trusting the full 60h race; switch RUN_DURATION_MIN to 3600 for the real let-it-rip run
// (and RUN_SPEED back to 1 — see below).
//
// RUN_SPEED=4 here, not 1: real observed Haiku call latency from the last canary's Langfuse
// traces was 1.5-2.7s (avg 1.8s). Tick interval is 15/speed seconds, and the brain-call
// semaphore caps concurrency at 5 regardless of tick rate — so as long as tick interval stays
// comfortably above worst-case latency, calls never queue up behind the semaphore and the
// sustained request rate is just 1/interval per second. speed=4 -> 3.75s/tick -> ~1s of margin
// over the worst observed call, ~16 req/min sustained (nowhere near any rate limit), and finishes
// the 300-tick canary in ~19 real minutes instead of 75. Do NOT push speed much higher than this
// for a canary — once tick interval drops below ~2.7s the semaphore starts staying pinned at 5
// concurrent, and sustained rate stops being speed-proportional and jumps to ~200-300 req/min.
const RUN_SPEED = 4;
const RUN_DURATION_MIN = 75;

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

/** The Command Center's bottom rail: brand mark, sim clock/weather, and start/connection
 * status — persistent chrome, not a modal (direction contract). */
export function Controls({ status }: { status: ConnectionStatus }) {
  const [starting, setStarting] = useState(false);
  const elapsedMin = useAppSelector((state) => state.race.elapsedMin);
  const environment = useAppSelector((state) => state.race.environment);

  async function handleStart() {
    setStarting(true);
    try {
      await fetch(`${API_BASE_URL}/run?speed=${RUN_SPEED}&duration_min=${RUN_DURATION_MIN}`, {
        method: "POST",
      });
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

        <Button onClick={handleStart} disabled={starting} size="sm">
          {starting ? "Starting…" : "Start"}
        </Button>
      </div>
    </Panel>
  );
}
