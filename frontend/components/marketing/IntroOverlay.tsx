"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { INTRO_GREETING, INTRO_SEEN_KEY, WORDMARK_LIGHT_SRC } from "@/lib/brand";
import {
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
 */
export function IntroOverlay() {
  const [active, setActive] = useState(false);
  const [motion, setMotion] = useState<IntroMotionFrame>(INITIAL_MOTION);
  const [fading, setFading] = useState(false);
  const startRef = useRef<number | null>(null);
  const frameRef = useRef<number | null>(null);
  const dismissedRef = useRef(false);

  const finish = useCallback(() => {
    if (dismissedRef.current) return;
    dismissedRef.current = true;
    try {
      sessionStorage.setItem(INTRO_SEEN_KEY, "1");
    } catch {
      // Private browsing may block storage; still dismiss.
    }
    setFading(true);
    window.setTimeout(() => setActive(false), 320);
  }, []);

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

    setActive(true);
    startRef.current = performance.now();
    setMotion(introMotionAt(0));

    const tick = (now: number) => {
      if (dismissedRef.current || startRef.current === null) return;
      const elapsed = now - startRef.current;
      const next = introMotionAt(elapsed);
      setMotion(next);
      if (next.phase === "done") {
        finish();
        return;
      }
      frameRef.current = requestAnimationFrame(tick);
    };

    frameRef.current = requestAnimationFrame(tick);

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") finish();
    };

    let scrollReady = false;
    const scrollTimer = window.setTimeout(() => {
      scrollReady = true;
    }, 450);

    const onScroll = () => {
      if (!scrollReady || window.scrollY < 64) return;
      finish();
    };

    window.addEventListener("keydown", onKeyDown);
    window.addEventListener("scroll", onScroll, { passive: true });

    return () => {
      window.clearTimeout(scrollTimer);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
      window.removeEventListener("keydown", onKeyDown);
      window.removeEventListener("scroll", onScroll);
    };
  }, [finish]);

  if (!active) return null;

  const { phase, logoMark, wordmark, greeting } = motion;

  return (
    <div
      className={`fixed inset-0 z-[100] flex items-center justify-center transition-opacity duration-300 motion-reduce:transition-none ${
        fading ? "pointer-events-none opacity-0" : "opacity-100"
      }`}
      data-intro-phase={phase}
      onClick={() => finish()}
      role="presentation"
      style={{
        background:
          "radial-gradient(circle at center, rgb(2 6 23) 0%, rgb(15 23 42) 62%, rgb(15 23 42) 82%, rgb(146 64 14) 94%, rgb(217 119 6) 100%)",
      }}
    >
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
      <div className="flex w-full max-w-2xl flex-col items-center px-6 text-center">
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
