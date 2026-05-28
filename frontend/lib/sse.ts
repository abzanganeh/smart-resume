"use client";

import { useEffect, useRef, useState } from "react";

export interface SSEEvent {
  event: string;
  phase?: number;
  message?: string;
  data?: unknown;
  output?: unknown;
  cost?: number;
  cost_formatted?: string;
  provider?: string;
  model?: string;
}

interface UseSSEResult {
  events: SSEEvent[];
  lastEvent: SSEEvent | null;
  isConnected: boolean;
  isDone: boolean;
  error: string | null;
  connect: (url: string) => void;
  reset: () => void;
}

export function useSSE(): UseSSEResult {
  const [events, setEvents] = useState<SSEEvent[]>([]);
  const [lastEvent, setLastEvent] = useState<SSEEvent | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isDone, setIsDone] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const sourceRef = useRef<EventSource | null>(null);

  const connect = (url: string) => {
    // Close any existing connection
    sourceRef.current?.close();
    setEvents([]);
    setLastEvent(null);
    setIsDone(false);
    setError(null);

    const es = new EventSource(url);
    sourceRef.current = es;
    setIsConnected(true);

    es.onmessage = (e) => {
      try {
        const parsed: SSEEvent = JSON.parse(e.data);
        setLastEvent(parsed);
        setEvents((prev) => [...prev, parsed]);

        if (parsed.event === "done" || parsed.event === "stream_end") {
          setIsDone(true);
          setIsConnected(false);
          es.close();
        }
        if (parsed.event === "error") {
          setError(parsed.message ?? "Unknown error");
          setIsConnected(false);
          es.close();
        }
      } catch {
        // ignore malformed events
      }
    };

    es.onerror = () => {
      setError("Connection lost. Please try again.");
      setIsConnected(false);
      es.close();
    };
  };

  const reset = () => {
    sourceRef.current?.close();
    setEvents([]);
    setLastEvent(null);
    setIsConnected(false);
    setIsDone(false);
    setError(null);
  };

  useEffect(() => {
    return () => {
      sourceRef.current?.close();
    };
  }, []);

  return { events, lastEvent, isConnected, isDone, error, connect, reset };
}
