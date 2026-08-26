"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown } from "lucide-react";
import { HeroMessageRotator } from "@/components/marketing/HeroMessageRotator";
import { HeroProductBackground } from "@/components/marketing/HeroProductBackground";
import { HERO_MESSAGES } from "@/lib/marketing/heroStrengths";
import {
  activeStageFromProgress,
  pinnedProgressForSticky,
} from "@/lib/marketing/stageRail";
import {
  heroMessageProgressFromTrack,
  heroScrollTrackHeightVh,
  PINNED_PANEL_HEIGHT_CLASS,
  PINNED_STICKY_TOP_CLASS,
  PINNED_STICKY_TOP_PX,
} from "@/lib/marketing/scrollPin";

const MESSAGE_COUNT = HERO_MESSAGES.length;

/**
 * Pinned hero scrollytelling with product art as the viewport background.
 * Badge sits below the nav with breathing room; scroll hint anchors the bottom.
 */
export function HeroScrollExperience() {
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    const motionQuery = window.matchMedia("(prefers-reduced-motion: reduce)");
    const applyMotion = () => setReducedMotion(motionQuery.matches);
    applyMotion();
    motionQuery.addEventListener("change", applyMotion);
    return () => motionQuery.removeEventListener("change", applyMotion);
  }, []);

  useEffect(() => {
    if (reducedMotion) return;

    const sync = () => {
      if (frameRef.current !== null) return;
      frameRef.current = requestAnimationFrame(() => {
        frameRef.current = null;
        const track = trackRef.current;
        if (!track) return;

        const rect = track.getBoundingClientRect();
        const progress = pinnedProgressForSticky(
          { top: rect.top, height: rect.height },
          window.innerHeight,
          PINNED_STICKY_TOP_PX,
        );
        setScrollProgress(progress);

        const messageProgress = heroMessageProgressFromTrack(
          progress,
          MESSAGE_COUNT,
        );
        const next = activeStageFromProgress(messageProgress, MESSAGE_COUNT);
        if (next !== null) {
          setActiveIndex((current) => (current === next ? current : next));
        }
      });
    };

    sync();
    window.addEventListener("scroll", sync, { passive: true });
    window.addEventListener("resize", sync, { passive: true });
    return () => {
      window.removeEventListener("scroll", sync);
      window.removeEventListener("resize", sync);
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    };
  }, [reducedMotion]);

  const backgroundFade =
    MESSAGE_COUNT <= 1 ? 0 : activeIndex / (MESSAGE_COUNT - 1);

  const pinnedPanel = (
    <>
      <HeroProductBackground fade={backgroundFade} />
      <div className="relative z-[1] flex min-h-0 flex-1 flex-col px-4 sm:px-6">
        <HeroMessageRotator activeIndex={activeIndex} layout="viewport" />
      </div>
      <div
        className="relative z-[1] shrink-0 flex flex-col items-center gap-1.5 px-4 pb-2 pt-2 text-slate-600 dark:text-slate-300"
        aria-hidden
      >
        <div className="flex items-center gap-1.5" aria-hidden>
          {HERO_MESSAGES.map((message, index) => (
            <span
              key={message.id}
              className={`h-1.5 rounded-full transition-all duration-300 ${
                index === activeIndex
                  ? "w-6 bg-amber-600 dark:bg-amber-400"
                  : "w-1.5 bg-slate-400/80 dark:bg-slate-500"
              }`}
            />
          ))}
        </div>
        <p className="text-xs font-medium drop-shadow-sm">
          {activeIndex >= MESSAGE_COUNT - 1
            ? "Keep scrolling for sign-up and the rest of the page"
            : "Scroll to explore each capability"}
        </p>
        {activeIndex < MESSAGE_COUNT - 1 && (
          <ChevronDown
            aria-hidden
            className="h-4 w-4 animate-bounce motion-reduce:animate-none"
          />
        )}
      </div>
    </>
  );

  if (reducedMotion) {
    return (
      <div
        className={`relative ${PINNED_PANEL_HEIGHT_CLASS} flex min-h-0 flex-col overflow-hidden rounded-none`}
      >
        {pinnedPanel}
      </div>
    );
  }

  return (
    <div
      ref={trackRef}
      className="hero-scroll-track relative z-[1] w-full"
      data-hero-scroll-track
      data-hero-active-index={activeIndex}
      data-scroll-progress={scrollProgress.toFixed(3)}
      style={{ height: `${heroScrollTrackHeightVh(MESSAGE_COUNT)}vh` }}
    >
      <div
        className={`sticky ${PINNED_STICKY_TOP_CLASS} ${PINNED_PANEL_HEIGHT_CLASS} flex min-h-0 flex-col overflow-hidden`}
      >
        {pinnedPanel}
      </div>
    </div>
  );
}
