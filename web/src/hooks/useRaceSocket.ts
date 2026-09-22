import { useEffect } from "react";
import mockRaceState from "../mocks/mockRaceState.json";
import { raceStateReceived } from "../store/raceSlice";
import { useAppDispatch } from "../store/hooks";
import type { RaceState } from "../types/models";

const WS_URL = import.meta.env.VITE_WS_URL as string;
const USE_MOCK_DATA = import.meta.env.VITE_USE_MOCK_DATA === "true";

/** Connects to the sim's WebSocket (multiple tabs/clients can each hold their own connection
 * — see ADR-0011, the backend broadcasts to every connected client) and dispatches each
 * incoming RaceState into the store. No reconnect/backoff logic yet — this is the first
 * vertical slice (ADR-0007); revisit once this is a longer-lived view than a dev tab.
 *
 * VITE_USE_MOCK_DATA=true skips the WS connection entirely and prefills the store with
 * src/mocks/mockRaceState.json once — for iterating on panels/monologue styling without a
 * backend running or a real race in progress. */
export function useRaceSocket() {
  const dispatch = useAppDispatch();

  useEffect(() => {
    if (USE_MOCK_DATA) {
      dispatch(raceStateReceived(mockRaceState as unknown as RaceState));
      return;
    }

    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      const raceState = JSON.parse(event.data) as RaceState;
      dispatch(raceStateReceived(raceState));
    };
    return () => socket.close();
  }, [dispatch]);
}
