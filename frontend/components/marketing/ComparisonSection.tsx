"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, Check, X } from "lucide-react";
import { PRODUCT_NAME } from "@/lib/brand";
import {
  COMPARISON_SCROLL_TRACK_VH,
  comparisonProgressFromTrack,
  PINNED_PANEL_HEIGHT_CLASS,
  PINNED_STICKY_TOP_CLASS,
  PINNED_STICKY_TOP_PX,
} from "@/lib/marketing/scrollPin";
import { pinnedProgressForSticky } from "@/lib/marketing/stageRail";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

const WITHOUT = [
  "Check a job board when you remember",
  "The role went up three days ago",
  "You are applicant 200",
  "Rewrite the resume by hand",
  "Apply late",
  "Never hear back",
];

const WITH = [
  "Name the companies you want",
  "Their careers pages are read every few minutes",
  "You hear the moment a role opens",
  "Tailor from your real experience",
  "Apply the same hour",
  "Track it automatically",
];

const FLIP_AT = 0.5;

function FlowList({
  lines,
  tone,
}: {
  lines: readonly string[];
  tone: "without" | "with";
}) {
  const arrowClass =
    tone === "with"
      ? "text-emerald-600 dark:text-emerald-500"
      : "text-slate-500 dark:text-slate-500";
  const textClass =
    tone === "with"
      ? "text-slate-700 dark:text-slate-300"
      : "text-slate-600 dark:text-slate-400";

  return (
    <ul className="space-y-2">
      {lines.map((line, index) => (
        <li key={line} className={`text-sm leading-snug sm:text-base ${textClass}`}>
          {line}
          {index < lines.length - 1 && (
            <ArrowDown aria-hidden className={`mt-1 h-3.5 w-3.5 ${arrowClass}`} />
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Pinned crossfade: the section title stays visible while scroll flips the
 * card from "On your own" to "With FlintApply". While the "on your own" side
 * is on screen an amber wash overrides the outer landing-scroll-band; the
 * wash fades out cleanly as the green "with FlintApply" side appears.
 */
export function ComparisonSection() {
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const [compareProgress, setCompareProgress] = useState(0);
  const flipped = compareProgress >= FLIP_AT;
  const overlayOpacity = 1 - compareProgress;

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
        setCompareProgress(comparisonProgressFromTrack(progress));
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

  return (
    <div className="relative">
      <div
        aria-hidden
        className="comparison-band-overlay"
        style={{ opacity: overlayOpacity }}
      />
      <section className={`${SECTION} relative pb-16`}>
        <div
          ref={trackRef}
          className="relative mx-auto max-w-4xl"
          data-comparison-scroll-track
          style={{ height: `${COMPARISON_SCROLL_TRACK_VH}vh` }}
        >
          <div
            className={`sticky ${PINNED_STICKY_TOP_CLASS} ${PINNED_PANEL_HEIGHT_CLASS} flex min-h-0 flex-col overflow-hidden py-4 sm:py-6`}
          >
            <header className="shrink-0 text-center">
              <h2 className={SECTION_HEADING}>Same goal, days earlier</h2>
              <p className={`${SECTION_SUBHEADING} mb-4 sm:mb-6`}>
                Scroll to compare doing it alone versus using {PRODUCT_NAME}.
              </p>
            </header>

            <div className="flex min-h-0 flex-1 items-center justify-center">
              <div
                className={`w-full max-w-2xl rounded-2xl border p-6 shadow-sm backdrop-blur-sm transition-colors duration-500 motion-reduce:transition-none sm:p-8 ${
                  flipped
                    ? "border-emerald-300 bg-emerald-50/85 dark:border-emerald-700/60 dark:bg-emerald-950/50"
                    : "border-slate-300 bg-white/85 dark:border-slate-700 dark:bg-slate-900/70"
                }`}
              >
                <div aria-hidden className="relative mb-5 h-7">
                  <span
                    className="absolute inset-0 flex items-center gap-2 text-base font-semibold text-slate-700 dark:text-slate-300"
                    style={{ opacity: 1 - compareProgress }}
                  >
                    <X className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
                    On your own
                  </span>
                  <span
                    className="absolute inset-0 flex items-center gap-2 text-base font-semibold text-emerald-800 dark:text-emerald-300"
                    style={{ opacity: compareProgress }}
                  >
                    <Check className="h-4 w-4 shrink-0" />
                    With {PRODUCT_NAME}
                  </span>
                </div>

                <div aria-hidden className="relative min-h-[18rem] sm:min-h-[20rem]">
                  <div
                    className="absolute inset-0"
                    style={{ opacity: 1 - compareProgress }}
                  >
                    <FlowList lines={WITHOUT} tone="without" />
                  </div>
                  <div
                    className="absolute inset-0"
                    style={{ opacity: compareProgress }}
                  >
                    <FlowList lines={WITH} tone="with" />
                  </div>
                </div>

                <div
                  aria-hidden
                  className="mt-5 h-1 w-full overflow-hidden rounded-full bg-slate-300 dark:bg-slate-700"
                >
                  <div
                    className="h-full rounded-full bg-emerald-500"
                    style={{ width: `${compareProgress * 100}%` }}
                  />
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="sr-only">
          <h2>Same goal, days earlier</h2>
          <h3>On your own</h3>
          <ul>
            {WITHOUT.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
          <h3>With {PRODUCT_NAME}</h3>
          <ul>
            {WITH.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </div>
      </section>
    </div>
  );
}
