"use client";
import { useEffect, useRef, useState } from "react";
import { createWS } from "./api";

export interface StreamEvent {
  agent?: string;
  type: string;
  data: unknown;
}

export function useAgentStream(engagementId: string | null) {
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!engagementId) return;
    const ws = createWS(engagementId);
    wsRef.current = ws;

    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      try {
        const ev: StreamEvent = JSON.parse(e.data);
        setEvents((prev) => [...prev.slice(-499), ev]);
      } catch {}
    };

    return () => {
      ws.close();
      setConnected(false);
    };
  }, [engagementId]);

  const send = (data: unknown) => {
    wsRef.current?.send(JSON.stringify(data));
  };

  return { events, connected, send };
}
