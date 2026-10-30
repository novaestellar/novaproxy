import { createContext, useContext, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import type { Status } from "./types";

type LiveState = {
  status: Status | null;
  connected: boolean;
};

const LiveContext = createContext<LiveState>({ status: null, connected: false });

export function LiveProvider({ children }: { children: ReactNode }) {
  const [status, setStatus] = useState<Status | null>(null);
  const [connected, setConnected] = useState(false);
  const sourceRef = useRef<EventSource | null>(null);

  useEffect(() => {
    let closed = false;
    let retry: number | undefined;

    const connect = () => {
      if (closed) return;
      const source = new EventSource("/api/stream");
      sourceRef.current = source;

      source.onopen = () => setConnected(true);
      source.onmessage = (event) => {
        try {
          setStatus(JSON.parse(event.data) as Status);
          setConnected(true);
        } catch {
          /* ignore malformed frame */
        }
      };
      source.onerror = () => {
        setConnected(false);
        source.close();
        if (!closed) retry = window.setTimeout(connect, 2500);
      };
    };

    connect();
    return () => {
      closed = true;
      clearTimeout(retry);
      sourceRef.current?.close();
    };
  }, []);

  return <LiveContext.Provider value={{ status, connected }}>{children}</LiveContext.Provider>;
}

export function useLive() {
  return useContext(LiveContext);
}
