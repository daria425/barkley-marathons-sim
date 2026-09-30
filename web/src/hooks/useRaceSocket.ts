import { useEffect, useRef, useState } from "react";
import mockRaceState from "../mocks/mockRaceState.json";
import { fromHistory } from "../lib/monologues";
import { fetchMonologuePage } from "../lib/monologueApi";
import { monologueHistoryLatestLoaded, raceStateReceived } from "../store/raceSlice";
import { store } from "../store/store";
import { useAppDispatch } from "../store/hooks";
import type { RaceState } from "../types/models";

const WS_URL = import.meta.env.VITE_WS_URL as string;
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";
const RECONNECT_DELAY_MS = 2000;

export type ConnectionStatus = "connecting" | "open" | "closed";

/** Connects to the sim's WebSocket (multiple tabs/clients can each hold their own connection
 * — see ADR-0011, the backend broadcasts to every connected client) and dispatches each
 * incoming RaceState into the store. Reconnects on drop with a fixed delay — good enough for
 * a dev tab left open across a backend restart; a real backoff/jitter policy is a later-phase
 * concern, not this vertical slice's (ADR-0007).
 *
 * VITE_USE_MOCK_DATA=true skips the WS connection entirely and prefills the store with
 * src/mocks/mockRaceState.json once — for iterating on panels/monologue styling without a
 * backend running or a real race in progress. */
export function useRaceSocket(): ConnectionStatus {
  const dispatch = useAppDispatch();
  const [status, setStatus] = useState<ConnectionStatus>(
    USE_MOCK_DATA ? "open" : "connecting",
  );
  const reconnectTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (USE_MOCK_DATA) {
      dispatch(raceStateReceived(mockRaceState as unknown as RaceState));
      return;
    }

    let cancelled = false;
    let socket: WebSocket;
    // Runners whose history has been backfilled on THIS connection. Reset on every (re)connect
    // so a reconnect refills whatever was missed while the socket was down.
    let backfilled = new Set<string>();

    // The WS only ever carries the latest decision, so the feed's history comes from the REST
    // endpoint (ADR-0021). A failure just leaves the feed live-only; "Load older" can retry.
    function backfillMonologues(raceState: RaceState) {
      for (const name of Object.keys(raceState.runners)) {
        if (backfilled.has(name)) continue;
        backfilled.add(name);
        const sinceSeq = store.getState().race.monologueMeta[name]?.liveSeq ?? 0;
        fetchMonologuePage(name)
          .then((page) => {
            if (cancelled) return;
            dispatch(
              monologueHistoryLatestLoaded({
                personaName: name,
                entries: fromHistory(page),
                hasMore: page.has_more,
                sinceSeq,
              }),
            );
          })
          .catch(() => backfilled.delete(name));
      }
    }

    function connect() {
      setStatus("connecting");
      backfilled = new Set();
      socket = new WebSocket(WS_URL);
      socket.onopen = () => !cancelled && setStatus("open");
      socket.onmessage = (event) => {
        const raceState = JSON.parse(event.data) as RaceState;
        dispatch(raceStateReceived(raceState));
        backfillMonologues(raceState);
      };
      socket.onclose = () => {
        if (cancelled) return;
        setStatus("closed");
        reconnectTimer.current = setTimeout(connect, RECONNECT_DELAY_MS);
      };
      socket.onerror = () => socket.close();
    }

    connect();
    return () => {
      cancelled = true;
      if (reconnectTimer.current) clearTimeout(reconnectTimer.current);
      socket.close();
    };
  }, [dispatch]);

  return status;
}
