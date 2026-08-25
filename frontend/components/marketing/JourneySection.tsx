"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowRight } from "lucide-react";
import { JOURNEY_STEPS, accessBadge } from "@/lib/marketing/journey";
import {
  journeyScrollTrackHeightVh,
  journeyStageProgressFromTrack,
  PINNED_PANEL_HEIGHT_CLASS,
  PINNED_STICKY_TOP_CLASS,
  PINNED_STICKY_TOP_PX,
} from "@/lib/marketing/scrollPin";
import {
  activeStageFromProgress,
  pinnedProgressForSticky,
  stageLetter,
  stageTheme,
} from "@/lib/marketing/stageRail";
import {
  FINE_PRINT,
  INLINE_CTA,
  SECTION,
  SECTION_HEADING,
  SECTION_SUBHEADING,
} from "./styles";

/**
 * Pinned scrollytelling journey.
 *
 * The section title stays visible while scrolling advances A → F in place.
 * The track is tall enough that each stage gets a full viewport of scroll
 * travel on a trackpad.
 */
export function JourneySection() {
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [railProgressValue, setRailProgressValue] = useState(0);

  useEffect(() => {
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
        setRailProgressValue(progress);

        const stageProgress = journeyStageProgressFromTrack(
          progress,
          JOURNEY_STEPS.length,
        );
        const next = activeStageFromProgress(stageProgress, JOURNEY_STEPS.length);
        if (next !== null) setActiveIndex(next);
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
  }, []);

  const goToStage = useCallback((index: number) => {
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const absoluteTop = rect.top + window.scrollY;
    const travel = rect.height - window.innerHeight;
    const share = (index + 0.5) / JOURNEY_STEPS.length;
    const target = travel <= 0 ? absoluteTop : absoluteTop + share * travel;
    window.scrollTo({ top: Math.max(0, target), behavior: "smooth" });
  }, []);

  const step = JOURNEY_STEPS[activeIndex];
  const theme = stageTheme(step.id);
  const badge = accessBadge(step.access);

  return (
    <section className={`${SECTION} pb-16`}>
      <div
        id="journey-track"
        ref={trackRef}
        className="relative mx-auto max-w-4xl"
        data-journey-scroll-track
        style={
          {
            height: `${journeyScrollTrackHeightVh(JOURNEY_STEPS.length)}vh`,
            "--rail-progress": railProgressValue,
          } as CSSProperties
        }
      >
        <div aria-hidden className="absolute inset-0 flex flex-col">
          {JOURNEY_STEPS.map((item) => (
            <div
              key={item.id}
              id={`stage-${item.id}`}
              data-journey-marker={item.id}
              className="flex-1 scroll-mt-24"
            />
          ))}
        </div>

        <div
          className={`sticky ${PINNED_STICKY_TOP_CLASS} ${PINNED_PANEL_HEIGHT_CLASS} flex min-h-0 flex-col overflow-hidden bg-gradient-to-br from-slate-100 via-white to-slate-200 py-4 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 sm:py-6`}
        >
          <header className="shrink-0 text-center">
            <h2 className={SECTION_HEADING}>Your job search, step by step</h2>
            <p className={`${SECTION_SUBHEADING} mb-4 sm:mb-6`}>
              Scroll to walk through each stage, or pick a letter. Badges show where a
              paid plan is required &mdash; everything else works on the free tier.
            </p>
          </header>

          <div
            className="grid min-h-0 flex-1 gap-4 lg:grid-cols-[2.75rem_minmax(0,1fr)] lg:gap-8 lg:items-center"
            style={{ "--stage-glow": theme.glow } as CSSProperties}
          >
            <nav
              aria-label="Stage letters"
              className="relative flex shrink-0 items-center justify-center gap-2 sm:gap-3 lg:flex-col lg:justify-center lg:gap-3"
            >
              <span
                aria-hidden
                className="absolute left-0 right-0 top-1/2 h-px -translate-y-1/2 bg-slate-300 dark:bg-slate-700 lg:bottom-0 lg:left-1/2 lg:right-auto lg:top-0 lg:h-auto lg:w-px lg:translate-y-0 lg:-translate-x-1/2"
              />
              <span
                aria-hidden
                className="absolute left-0 top-1/2 h-px -translate-y-1/2 bg-[rgb(var(--stage-glow))] lg:hidden"
                style={{ width: "calc(var(--rail-progress) * 100%)" }}
              />
              <span
                aria-hidden
                className="absolute left-1/2 top-0 hidden w-px -translate-x-1/2 bg-[rgb(var(--stage-glow))] lg:block"
                style={{ height: "calc(var(--rail-progress) * 100%)" }}
              />

              {JOURNEY_STEPS.map((item, index) => {
                const letterTheme = stageTheme(item.id);
                const isActive = index === activeIndex;
                return (
                  <span key={item.id} className="relative">
                    <button
                      type="button"
                      aria-current={isActive ? "step" : undefined}
                      aria-label={`${stageLetter(index)} — ${item.title}`}
                      data-active={isActive ? "true" : "false"}
                      onClick={() => goToStage(index)}
                      className={`relative z-[1] flex h-10 w-10 sm:h-11 sm:w-11 items-center justify-center rounded-full border font-mono text-sm font-bold transition-all duration-300 motion-reduce:transition-none motion-reduce:scale-100 ${
                        isActive
                          ? `scale-110 shadow-lg ${letterTheme.badge} ${letterTheme.text} ${letterTheme.border}`
                          : "scale-95 border-slate-300 bg-white text-slate-500 hover:scale-100 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
                      }`}
                    >
                      {stageLetter(index)}
                    </button>

                    {isActive && (
                      <>
                        <span
                          aria-hidden
                          className="absolute left-1/2 top-full h-4 w-px -translate-x-1/2 bg-[rgb(var(--stage-glow))] lg:hidden"
                        />
                        <span
                          aria-hidden
                          className="absolute left-full top-1/2 hidden h-px w-8 -translate-y-1/2 bg-[rgb(var(--stage-glow))] lg:block"
                        />
                      </>
                    )}
                  </span>
                );
              })}
            </nav>

            <article
              id="journey-panel"
              data-active-stage={step.id}
              aria-live="polite"
              className={`flex min-h-0 flex-1 flex-col justify-center rounded-2xl border-l-4 border-y border-r bg-white/70 p-5 shadow-sm transition-colors duration-500 motion-reduce:transition-none dark:bg-slate-900/60 sm:p-7 ${theme.border}`}
              style={{ borderLeftColor: "rgb(var(--stage-glow))" }}
            >
              <div className="mb-2 flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                <span>
                  {stageLetter(activeIndex)} · Stage {activeIndex + 1} of{" "}
                  {JOURNEY_STEPS.length}
                </span>
              </div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100 sm:text-xl">
                  {step.title}
                </h3>
                {badge && (
                  <span className="rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300">
                    {badge}
                  </span>
                )}
              </div>
              <p className="text-sm leading-relaxed text-slate-600 dark:text-slate-400 sm:text-base">
                {step.description}
              </p>
              {step.accessNote && (
                <p className={`mt-3 ${FINE_PRINT}`}>{step.accessNote}</p>
              )}
              <Link href={step.ctaHref} className={`${INLINE_CTA} mt-4 inline-flex sm:mt-5`}>
                {step.ctaLabel}
                <ArrowRight aria-hidden className="h-4 w-4" />
              </Link>
            </article>
          </div>
        </div>
      </div>

      <div className="sr-only">
        <h2>Your job search, step by step</h2>
        <ol aria-label="Job search stages">
          {JOURNEY_STEPS.map((item, index) => {
            const itemBadge = accessBadge(item.access);
            return (
              <li key={item.id}>
                <h3>
                  {stageLetter(index)} — {item.title}
                </h3>
                {itemBadge && <span>{itemBadge}</span>}
                <p>{item.description}</p>
                {item.accessNote && <p>{item.accessNote}</p>}
                <a href={item.ctaHref}>{item.ctaLabel}</a>
              </li>
            );
          })}
        </ol>
      </div>
    </section>
  );
}
