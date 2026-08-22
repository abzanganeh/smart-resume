"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { ArrowRight } from "lucide-react";
import { JOURNEY_STEPS, accessBadge } from "@/lib/marketing/journey";
import {
  activeStageFromProgress,
  pinnedProgress,
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

/** Scroll distance allotted to each stage, as a share of the viewport. */
const SEGMENT_VH = 58;

/**
 * Pinned scrollytelling journey.
 *
 * The track is tall enough to give each stage its own slice of scroll; the
 * letters and the panel are pinned inside it, so scrolling advances A → F in
 * place rather than moving past a stack of cards. Scroll position never enters
 * React state as a coordinate — one rAF-coalesced listener derives the active
 * index and writes the rail fill as a CSS variable.
 *
 * The full copy for every stage also renders in the screen-reader list, so
 * crawlers and no-JS clients get all six descriptions.
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
        const progress = pinnedProgress(
          { top: rect.top, height: rect.height },
          window.innerHeight,
        );
        setRailProgressValue(progress);

        const next = activeStageFromProgress(progress, JOURNEY_STEPS.length);
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

  /**
   * Scroll to the middle of a stage's band so that stage reads as active.
   *
   * Derived from the same pinned-travel geometry as `pinnedProgress` rather
   * than from the marker offsets — the markers divide the whole track, but only
   * `height - viewport` of it is scrollable while the panel is pinned, so
   * targeting a marker directly overshoots by up to a full stage.
   */
  const goToStage = useCallback((index: number) => {
    const track = trackRef.current;
    if (!track) return;
    const rect = track.getBoundingClientRect();
    const absoluteTop = rect.top + window.scrollY;
    const travel = rect.height - window.innerHeight;
    const share = (index + 0.5) / JOURNEY_STEPS.length;
    const target = travel <= 0 ? absoluteTop : absoluteTop + share * travel;
    window.scrollTo({ top: Math.max(0, target), behavior: "instant" });
  }, []);

  const step = JOURNEY_STEPS[activeIndex];
  const theme = stageTheme(step.id);
  const badge = accessBadge(step.access);

  return (
    <section className={`${SECTION} pb-16`}>
      <h2 className={SECTION_HEADING}>Your job search, step by step</h2>
      <p className={`${SECTION_SUBHEADING} mb-8`}>
        Scroll to walk through each stage, or pick a letter. Badges show where a
        paid plan is required &mdash; everything else works on the free tier.
      </p>

      <div
        ref={trackRef}
        className="relative mx-auto max-w-4xl"
        style={
          {
            height: `${JOURNEY_STEPS.length * SEGMENT_VH}vh`,
            "--rail-progress": railProgressValue,
          } as CSSProperties
        }
      >
        {/* Scroll slices: they give each stage its own scroll distance and
            double as deep-link anchors. Absolutely positioned so they add no
            layout height of their own. */}
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

        <div className="sticky top-24">
          <div
            className="grid gap-6 lg:grid-cols-[2.75rem_minmax(0,1fr)] lg:gap-10"
            style={{ "--stage-glow": theme.glow } as CSSProperties}
          >
            <nav
              aria-label="Stage letters"
              className="relative flex items-center justify-center gap-3 lg:flex-col lg:justify-start lg:gap-4"
            >
              {/* Rail track: horizontal on small screens, vertical on desktop. */}
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
                      className={`relative z-[1] flex h-11 w-11 items-center justify-center rounded-full border font-mono text-sm font-bold transition-all duration-300 motion-reduce:transition-none motion-reduce:scale-100 ${
                        isActive
                          ? `scale-110 shadow-lg ${letterTheme.badge} ${letterTheme.text} ${letterTheme.border}`
                          : "scale-95 border-slate-300 bg-white text-slate-500 hover:scale-100 hover:border-slate-400 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-400"
                      }`}
                    >
                      {stageLetter(index)}
                    </button>

                    {/* Connector from the active letter to the panel. */}
                    {isActive && (
                      <>
                        <span
                          aria-hidden
                          className="absolute left-1/2 top-full h-6 w-px -translate-x-1/2 bg-[rgb(var(--stage-glow))] lg:hidden"
                        />
                        <span
                          aria-hidden
                          className="absolute left-full top-1/2 hidden h-px w-10 -translate-y-1/2 bg-[rgb(var(--stage-glow))] lg:block"
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
              className={`min-h-[19rem] rounded-2xl border-l-4 border-y border-r bg-white/70 p-6 shadow-sm transition-colors duration-500 motion-reduce:transition-none dark:bg-slate-900/60 sm:p-8 ${theme.border}`}
              style={{ borderLeftColor: "rgb(var(--stage-glow))" }}
            >
              <div className="mb-2 flex items-center gap-2 font-mono text-xs font-bold uppercase tracking-widest text-slate-500 dark:text-slate-400">
                <span>
                  {stageLetter(activeIndex)} · Stage {activeIndex + 1} of{" "}
                  {JOURNEY_STEPS.length}
                </span>
              </div>
              <div className="mb-3 flex flex-wrap items-center gap-2">
                <h3 className="text-xl font-semibold text-slate-900 dark:text-slate-100">
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
              <Link href={step.ctaHref} className={`${INLINE_CTA} mt-5 inline-flex`}>
                {step.ctaLabel}
                <ArrowRight aria-hidden className="h-4 w-4" />
              </Link>
            </article>
          </div>
        </div>
      </div>

      <ol aria-label="Job search stages" className="sr-only">
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
    </section>
  );
}
