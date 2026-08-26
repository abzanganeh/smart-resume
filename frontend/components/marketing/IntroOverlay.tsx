"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { INTRO_GREETING, INTRO_SEEN_KEY, WORDMARK_LIGHT_SRC } from "@/lib/brand";
import {
  INTRO_DISMISS_SLACK_MS,
  INTRO_FADE_MS,
  INTRO_FALLBACK_TICK_MS,
  INTRO_SCROLL_LOCK_CLASS,
  INTRO_TOTAL_MS,
  introMotionAt,
  shouldPlayIntro,
  type IntroMotionFrame,
} from "@/lib/marketing/intro";

const INITIAL_MOTION: IntroMotionFrame = introMotionAt(0);

/** Wordmark intrinsic size — matches `BrandLogo` text lockup. */
const WORDMARK_W = 2172;
const WORDMARK_H = 724;

function layerStyle(motion: { scale: number; opacity: number }) {
  return {
    opacity: motion.opacity,
    transform: `scale(${motion.scale})`,
    transformOrigin: "center center",
  };
}

/**
 * One-shot landing intro: icon → wordmark → greeting, stacked vertically.
 *
 * All three slots are reserved from the first frame so nothing shifts vertically
 * when the next layer emerges. Only opacity/scale animate — no translate.
 *
 * The timeline is driven from wall clock by two independent sources, and is
 * dismissed by an unconditional backstop timer. `requestAnimationFrame` alone
 * is not survivable here: browsers pause it for backgrounded or occluded tabs,
 * which left this full-viewport overlay pinned open indefinitely.
 */
export function IntroOverlay() {
  const [active, setActive] = useState(false);
  const [motion, setMotion] = useState<IntroMotionFrame>(INITIAL_MOTION);
  const [fading, setFading] = useState(false);
  const startRef = useRef<number | null>(null);
  const frameRef = useRef<number | null>(null);
  const intervalRef = useRef<number | null>(null);
  const backstopRef = useRef<number | null>(null);
  const fadeRef = useRef<number | null>(null);
  const dismissedRef = useRef(false);

  const clearDrivers = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    if (intervalRef.current !== null) {
      window.clearInterval(intervalRef.current);
      intervalRef.current = null;
    }
    if (backstopRef.current !== null) {
      window.clearTimeout(backstopRef.current);
      backstopRef.current = null;
    }
  }, []);

  const finish = useCallback(() => {
    if (dismissedRef.current) return;
    dismissedRef.current = true;
    clearDrivers();
    try {
      sessionStorage.setItem(INTRO_SEEN_KEY, "1");
    } catch {
      // Private browsing may block storage; still dismiss.
    }
    setFading(true);
    fadeRef.current = window.setTimeout(() => setActive(false), INTRO_FADE_MS);
  }, [clearDrivers]);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const forceReplay =
      new URLSearchParams(window.location.search).get("intro") === "1";

    let alreadyPlayed = false;
    try {
      alreadyPlayed =
        !forceReplay && sessionStorage.getItem(INTRO_SEEN_KEY) === "1";
    } catch {
      alreadyPlayed = false;
    }

    if (
      !shouldPlayIntro({
        prefersReducedMotion: motionQuery.matches,
        alreadyPlayed,
      })
    ) {
      return;
    }

    let started = false;

    /** Recompute from wall clock. Returns true once the timeline is over. */
    const sample = (): boolean => {
      if (dismissedRef.current || startRef.current === null) return true;
      const next = introMotionAt(performance.now() - startRef.current);
      setMotion(next);
      if (next.phase === "done") {
        finish();
        return true;
      }
      return false;
    };

    const tick = () => {
      if (sample()) return;
      frameRef.current = requestAnimationFrame(tick);
    };

    const start = () => {
      if (started || dismissedRef.current) return;
      started = true;
      window.scrollTo({ top: 0, left: 0, behavior: "instant" });
      startRef.current = performance.now();
      setActive(true);
      setMotion(introMotionAt(0));
      frameRef.current = requestAnimationFrame(tick);
      intervalRef.current = window.setInterval(sample, INTRO_FALLBACK_TICK_MS);
      backstopRef.current = window.setTimeout(
        finish,
        INTRO_TOTAL_MS + INTRO_DISMISS_SLACK_MS,
      );
    };

    // Playing a 12s intro to a hidden tab burns the once-per-session budget on
    // nobody, so wait until the page is actually on screen.
    const onVisible = () => {
      if (document.visibilityState !== "visible") return;
      if (!started) {
        start();
        return;
      }
      sample();
    };

    if (document.visibilityState === "visible") start();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };

    document.addEventListener("visibilitychange", onVisible);
    window.addEventListener("focus", onVisible);
    window.addEventListener("keydown", onKeyDown);

    return () => {
      if (fadeRef.current !== null) window.clearTimeout(fadeRef.current);
      clearDrivers();
      document.removeEventListener("visibilitychange", onVisible);
      window.removeEventListener("focus", onVisible);
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [finish, clearDrivers]);

  /** Keep the landing page at the top and non-scrollable while intro plays. */
  useEffect(() => {
    if (!active) {
      document.documentElement.classList.remove(INTRO_SCROLL_LOCK_CLASS);
      return;
    }

    window.scrollTo({ top: 0, left: 0, behavior: "instant" });
    document.documentElement.classList.add(INTRO_SCROLL_LOCK_CLASS);

    const blockScroll = (event: Event) => {
      event.preventDefault();
    };

    window.addEventListener("wheel", blockScroll, { passive: false });
    window.addEventListener("touchmove", blockScroll, { passive: false });

    return () => {
      window.removeEventListener("wheel", blockScroll);
      window.removeEventListener("touchmove", blockScroll);
      document.documentElement.classList.remove(INTRO_SCROLL_LOCK_CLASS);
    };
  }, [active]);

  if (!active) return null;

  const { phase, logoMark, wordmark, greeting } = motion;

  return (
    <div
      className={`intro-overlay-backdrop fixed inset-0 z-[100] flex items-center justify-center transition-opacity duration-300 motion-reduce:transition-none ${
        fading ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
      data-intro-phase={phase}
      onClick={() => finish()}
      role="presentation"
    >
      {/*
        Decorative motion behind the brand stack — three independently animated
        layers so the intro reads as alive rather than a static plate. The
        content stack sits above these via z-index.
      */}
      <div aria-hidden className="intro-overlay-scene">
        <div className="intro-overlay-aurora" />
        <div className="intro-overlay-glow-core" />
        <div className="intro-overlay-shimmer" />
      </div>

      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          finish();
        }}
        className="absolute top-6 right-6 z-10 rounded-lg border border-amber-200/25 bg-slate-950/70 px-4 py-2 text-sm font-medium text-amber-50 hover:bg-slate-900/80 transition-colors"
      >
        Skip intro
      </button>

      {/* Fixed-height slots — layout never reflows when a layer fades in. */}
      <div className="relative z-[1] flex w-full max-w-2xl flex-col items-center px-6 text-center">
        <div className="flex h-40 w-full items-center justify-center sm:h-48">
          <div
            aria-hidden={logoMark.opacity < 0.05}
            className="motion-reduce:transform-none"
            style={layerStyle(logoMark)}
          >
            <BrandLogo
              showWordmark={false}
              className="h-32 w-32 sm:h-40 sm:w-40"
              priority
            />
          </div>
        </div>

        <div className="flex h-20 w-full items-center justify-center sm:h-24">
          <div
            aria-hidden={wordmark.opacity < 0.05}
            className="motion-reduce:transform-none"
            style={layerStyle(wordmark)}
          >
            <Image
              src={WORDMARK_LIGHT_SRC}
              alt=""
              width={WORDMARK_W}
              height={WORDMARK_H}
              className="h-16 w-auto sm:h-20"
              priority
              unoptimized
            />
          </div>
        </div>

        <div className="flex min-h-[7.5rem] w-full items-center justify-center sm:min-h-[8.5rem]">
          <div
            aria-hidden={greeting.opacity < 0.05}
            className="max-w-xl space-y-3 motion-reduce:transform-none"
            style={layerStyle(greeting)}
          >
            <p className="text-4xl font-bold tracking-tight text-white sm:text-6xl">
              {INTRO_GREETING.line}
            </p>
            <p className="text-base leading-relaxed text-amber-100/90 sm:text-lg">
              {INTRO_GREETING.sub}
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
