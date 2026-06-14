"use client";

import { useCallback, useRef, useState } from "react";

const MAX_STEPS = 20;

export function useVersionStack<T>(initial: T) {
  const [present, setPresent] = useState(initial);
  const pastRef = useRef<T[]>([]);
  const futureRef = useRef<T[]>([]);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const syncFlags = useCallback(() => {
    setCanUndo(pastRef.current.length > 0);
    setCanRedo(futureRef.current.length > 0);
  }, []);

  const push = useCallback(
    (next: T) => {
      pastRef.current = [...pastRef.current.slice(-(MAX_STEPS - 1)), present];
      futureRef.current = [];
      setPresent(next);
      syncFlags();
    },
    [present, syncFlags]
  );

  const replace = useCallback((next: T) => {
    setPresent(next);
  }, []);

  const reset = useCallback(
    (next: T) => {
      pastRef.current = [];
      futureRef.current = [];
      setPresent(next);
      syncFlags();
    },
    [syncFlags],
  );

  const undo = useCallback((): T | null => {
    if (pastRef.current.length === 0) return null;
    const prev = pastRef.current[pastRef.current.length - 1];
    pastRef.current = pastRef.current.slice(0, -1);
    futureRef.current = [present, ...futureRef.current].slice(0, MAX_STEPS);
    setPresent(prev);
    syncFlags();
    return prev;
  }, [present, syncFlags]);

  const redo = useCallback((): T | null => {
    if (futureRef.current.length === 0) return null;
    const next = futureRef.current[0];
    futureRef.current = futureRef.current.slice(1);
    pastRef.current = [...pastRef.current, present].slice(-MAX_STEPS);
    setPresent(next);
    syncFlags();
    return next;
  }, [present, syncFlags]);

  return { present, push, replace, reset, undo, redo, canUndo, canRedo };
}
