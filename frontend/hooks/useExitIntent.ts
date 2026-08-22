"use client";

import { useEffect, useRef } from "react";

/**
 * Desktop exit-intent: pointer leaves the viewport through the top edge.
 * Intentionally omitted on coarse pointers (typical phones/tablets).
 */
export function useExitIntent(onExitIntent: () => void, enabled: boolean): void {
  const callbackRef = useRef(onExitIntent);

  useEffect(() => {
    callbackRef.current = onExitIntent;
  }, [onExitIntent]);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;

    const coarse = window.matchMedia("(pointer: coarse)").matches;
    if (coarse) return;

    const handleMouseOut = (event: MouseEvent) => {
      if (event.clientY > 12) return;
      const related = event.relatedTarget as Node | null;
      if (related !== null) return;
      callbackRef.current();
    };

    document.documentElement.addEventListener("mouseout", handleMouseOut);
    return () => {
      document.documentElement.removeEventListener("mouseout", handleMouseOut);
    };
  }, [enabled]);
}
