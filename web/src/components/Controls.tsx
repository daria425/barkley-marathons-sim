import { useState } from "react";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;
const SPEEDS = [1, 60, 600] as const;

/** Start-only for this first slice (ADR-0007) — no pause/reset/quit-bugle yet, per
 * CLAUDE.md's Frontend section; those come once the map/watch/feed are proven out. */
export function Controls() {
  const [speed, setSpeed] = useState<(typeof SPEEDS)[number]>(60);
  const [status, setStatus] = useState<string | null>(null);

  async function handleStart() {
    setStatus("running...");
    const res = await fetch(`${API_BASE_URL}/run?speed=${speed}`, {
      method: "POST",
    });
    const body = await res.json();
    setStatus(body.status);
  }

  return (
    <div className="controls">
      <select
        value={speed}
        onChange={(e) => setSpeed(Number(e.target.value) as typeof speed)}
      >
        {SPEEDS.map((s) => (
          <option key={s} value={s}>
            {s}x
          </option>
        ))}
      </select>
      <button onClick={handleStart}>Start</button>
      {status && <span className="controls__status">{status}</span>}
    </div>
  );
}
