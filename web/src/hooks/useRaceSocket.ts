import { useEffect } from "react";
import { raceStateReceived } from "../store/raceSlice";
import { useAppDispatch } from "../store/hooks";
import type { RaceState } from "../types/models";

const WS_URL = import.meta.env.VITE_WS_URL as string;

/** Connects to the sim's WebSocket (multiple tabs/clients can each hold their own connection
 * — see ADR-0011, the backend broadcasts to every connected client) and dispatches each
 * incoming RaceState into the store. No reconnect/backoff logic yet — this is the first
 * vertical slice (ADR-0007); revisit once this is a longer-lived view than a dev tab. */
export function useRaceSocket() {
  const dispatch = useAppDispatch();

  useEffect(() => {
    const socket = new WebSocket(WS_URL);
    socket.onmessage = (event) => {
      const raceState = JSON.parse(event.data) as RaceState;
      dispatch(raceStateReceived(raceState));
    };
    return () => socket.close();
  }, [dispatch]);
}
