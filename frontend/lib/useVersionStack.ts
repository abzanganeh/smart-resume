"use client";

import { useCallback, useEffect, useRef, useState } from "react";

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

  const undo = useCallback(() => {
    if (pastRef.current.length === 0) return;
    const prev = pastRef.current[pastRef.current.length - 1];
    pastRef.current = pastRef.current.slice(0, -1);
    futureRef.current = [present, ...futureRef.current].slice(0, MAX_STEPS);
    setPresent(prev);
    syncFlags();
  }, [present, syncFlags]);

  const redo = useCallback(() => {
    if (futureRef.current.length === 0) return;
    const next = futureRef.current[0];
    futureRef.current = futureRef.current.slice(1);
    pastRef.current = [...pastRef.current, present].slice(-MAX_STEPS);
    setPresent(next);
    syncFlags();
  }, [present, syncFlags]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const mod = e.metaKey || e.ctrlKey;
      if (!mod) return;
      if (e.key === "z" && !e.shiftKey) {
        e.preventDefault();
        undo();
      } else if (e.key === "y" || (e.key === "z" && e.shiftKey)) {
        e.preventDefault();
        redo();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);

  return { present, push, replace, undo, redo, canUndo, canRedo };
}
