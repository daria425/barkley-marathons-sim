import { Flag, Timer } from "lucide-react";
import type { RunnerState } from "@/types/models";
import { endStatus, OUTCOME_LABELS, outcomeMessage } from "@/lib/raceOutcome";

export function BugleIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M3 9h5c5 0 8-2 11-5v13c-3-3-6-5-11-5H3M3 7v7M19 4h2v13h-2M7 12v4a4 4 0 0 0 8 0v-2" />
    </svg>
  );
}

export function OutcomeIcon({ status }: { status: NonNullable<ReturnType<typeof endStatus>> }) {
  return status === "finished" ? <Flag size={20} />
    : status === "dnf_cutoff" ? <Timer size={20} /> : <BugleIcon />;
}

export function RaceOutcome({ runner }: { runner: RunnerState }) {
  const status = endStatus(runner);
  if (!status) return null;
  return (
    <section className={`race-outcome outcome-${status}`} aria-label="Race result">
      <div className="outcome-eyebrow"><OutcomeIcon status={status} /><span>{OUTCOME_LABELS[status]}</span></div>
      <p className="outcome-message" role="status">{outcomeMessage(runner)}</p>
      <a className="outcome-project" href="https://github.com/daria425/barkley-marathons-sim" target="_blank" rel="noopener noreferrer">
        See project details on <span>https://github.com/daria425/barkley-marathons-sim</span>
      </a>
    </section>
  );
}
