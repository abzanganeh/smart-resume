"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Pause, Play } from "lucide-react";
import { HERO_STRENGTHS } from "@/lib/marketing/heroStrengths";
import {
  HERO_STRENGTH_ROTATION_MS,
  nextStrengthIndex,
  resyncRotationClock,
  shouldAdvanceStrengthRotation,
} from "@/lib/marketing/heroStrengthRotation";

const STRENGTH_COUNT = HERO_STRENGTHS.length;

/**
 * Cross-fading strength lines beneath the fixed hero headline.
 *
 * - All variants ship in the DOM for crawlers; inactive lines are hidden with CSS.
 * - WCAG 2.2.2: pausable via control, hover, and focus.
 * - Screen readers get a static list; the animated region is aria-hidden.
 */
export function HeroStrengthRotator() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [userPaused, setUserPaused] = useState(false);
  const [hoverPaused, setHoverPaused] = useState(false);
  const [focusPaused, setFocusPaused] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);
  const [documentHidden, setDocumentHidden] = useState(false);

  const lastAdvanceRef = useRef<number>(0);
  const intervalRef = useRef<number | null>(null);

  const paused = userPaused || hoverPaused || focusPaused || reducedMotion;

  const clearIntervalDriver = useCallback(() => {
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
  }, []);

  const tick = useCallback(() => {
    const now = performance.now();
    if (
      !shouldAdvanceStrengthRotation({
        now,
        lastAdvanceAt: lastAdvanceRef.current,
        intervalMs: HERO_STRENGTH_ROTATION_MS,
        paused,
        documentHidden,
        count: STRENGTH_COUNT,
      })
    ) {
      return;
    }
    setActiveIndex((current) => nextStrengthIndex(current, STRENGTH_COUNT));
    lastAdvanceRef.current = now;
  }, [paused, documentHidden]);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const applyMotion = () => setReducedMotion(motionQuery.matches);
    applyMotion();
    motionQuery.addEventListener("change", applyMotion);

    const onVisibility = () => {
      const hidden = document.visibilityState === "hidden";
      setDocumentHidden(hidden);
      if (!hidden) {
        lastAdvanceRef.current = resyncRotationClock(performance.now());
      }
    };
    onVisibility();
    document.addEventListener("visibilitychange", onVisibility);

    lastAdvanceRef.current = performance.now();
    intervalRef.current = window.setInterval(tick, 500);

    return () => {
      motionQuery.removeEventListener("change", applyMotion);
      document.removeEventListener("visibilitychange", onVisibility);
      clearIntervalDriver();
    };
  }, [tick, clearIntervalDriver]);

  const togglePause = () => {
    setUserPaused((value) => {
      const next = !value;
      if (!next) {
        lastAdvanceRef.current = resyncRotationClock(performance.now());
      }
      return next;
    });
  };

  const displayIndex = reducedMotion ? 0 : activeIndex;
  const showPauseControl = !reducedMotion && STRENGTH_COUNT > 1;

  return (
    <div className="hero-strength-rotator mx-auto mb-3 max-w-2xl">
      <ul className="sr-only">
        {HERO_STRENGTHS.map((strength) => (
          <li key={strength.id}>{strength.line}</li>
        ))}
      </ul>

      <div
        aria-hidden="true"
        className="hero-strength-rotator__stage text-lg sm:text-xl text-slate-600 dark:text-slate-400"
        data-active-index={displayIndex}
        onMouseEnter={() => setHoverPaused(true)}
        onMouseLeave={() => setHoverPaused(false)}
        onFocusCapture={() => setFocusPaused(true)}
        onBlurCapture={() => setFocusPaused(false)}
      >
        {HERO_STRENGTHS.map((strength, index) => (
          <p
            key={strength.id}
            className={
              index === displayIndex
                ? "hero-strength-rotator__line is-active"
                : "hero-strength-rotator__line"
            }
            data-strength-id={strength.id}
          >
            {strength.line}
          </p>
        ))}
      </div>

      {showPauseControl && (
        <button
          type="button"
          onClick={togglePause}
          className="hero-strength-rotator__pause mt-2 inline-flex items-center gap-1.5 rounded-lg border border-slate-300/80 bg-white/70 px-2.5 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900/70 dark:text-slate-300 dark:hover:bg-slate-800/80"
          aria-pressed={userPaused}
          aria-label={userPaused ? "Resume strength rotation" : "Pause strength rotation"}
        >
          {userPaused ? (
            <>
              <Play aria-hidden className="h-3.5 w-3.5" />
              Resume
            </>
          ) : (
            <>
              <Pause aria-hidden className="h-3.5 w-3.5" />
              Pause
            </>
          )}
        </button>
      )}
    </div>
  );
}
