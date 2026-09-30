import type { MonologueHistory } from "@/types/models";
import { PAGE_SIZE } from "@/lib/monologues";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

/** One page of a runner's past monologues from GET /monologues/{persona} — the latest page, or
 * the page before `before` (an entry id). Throws on a non-OK response. */
export async function fetchMonologuePage(
  personaName: string,
  before?: number,
): Promise<MonologueHistory> {
  const params = new URLSearchParams({ limit: String(PAGE_SIZE) });
  if (before !== undefined) params.set("before", String(before));
  const res = await fetch(
    `${API_BASE_URL}/monologues/${encodeURIComponent(personaName)}?${params}`,
  );
  if (!res.ok) throw new Error(`monologue history request failed: ${res.status}`);
  return (await res.json()) as MonologueHistory;
}
