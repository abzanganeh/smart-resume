"use client";

import { useEffect, useRef, useState } from "react";
import { ArrowDown, Check, X } from "lucide-react";
import { PRODUCT_NAME } from "@/lib/brand";
import { pinnedProgress } from "@/lib/marketing/stageRail";
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

/**
 * Crossfade midpoint. Below this the "on your own" flow is authoritative for
 * the discrete styling (border, heading emphasis); above it, the product flow.
 */
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
    <ul className="space-y-1.5">
      {lines.map((line, index) => (
        <li key={line} className={`text-sm leading-snug ${textClass}`}>
          {line}
          {index < lines.length - 1 && (
            <ArrowDown aria-hidden className={`mt-1 h-3 w-3 ${arrowClass}`} />
          )}
        </li>
      ))}
    </ul>
  );
}

/**
 * Pinned crossfade: the card reads "On your own" when the track pins and
 * becomes "With FlintApply" by the time it releases.
 *
 * Opacity is driven straight from a scroll-derived custom property with no CSS
 * transition on it — a transition on a value that changes every frame lags
 * behind the scroll and never settles on the target.
 */
export function ComparisonSection() {
  const trackRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const [compareProgress, setCompareProgress] = useState(0);
  const flipped = compareProgress >= FLIP_AT;

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
        setCompareProgress(progress);
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
    <section className={`${SECTION} pb-16`}>
      <h2 className={SECTION_HEADING}>Same goal, days earlier</h2>
      <p className={SECTION_SUBHEADING}>
        Scroll to compare doing it alone versus using {PRODUCT_NAME}.
      </p>

      <div
        ref={trackRef}
        className="relative mx-auto h-[180vh] max-w-md"
      >
        <div className="sticky top-24">
          <div
            className={`rounded-2xl border p-6 transition-colors duration-500 motion-reduce:transition-none sm:p-8 ${
              flipped
                ? "border-emerald-300 bg-emerald-50/70 dark:border-emerald-700/60 dark:bg-emerald-950/30"
                : "border-slate-300 bg-slate-100/60 dark:border-slate-700 dark:bg-slate-800/50"
            }`}
          >
            <div aria-hidden className="relative mb-5 h-6">
              <span
                className="absolute inset-0 flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300"
                style={{ opacity: 1 - compareProgress }}
              >
                <X className="h-4 w-4 shrink-0 text-red-600 dark:text-red-400" />
                On your own
              </span>
              <span
                className="absolute inset-0 flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300"
                style={{ opacity: compareProgress }}
              >
                <Check className="h-4 w-4 shrink-0" />
                With {PRODUCT_NAME}
              </span>
            </div>

            {/* Sized for the longer of the two flows so neither list clips. */}
            <div aria-hidden className="relative min-h-[17rem]">
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
              className="mt-4 h-0.5 w-full overflow-hidden rounded-full bg-slate-300 dark:bg-slate-700"
            >
              <div
                className="h-full rounded-full bg-emerald-500"
                style={{ width: `${compareProgress * 100}%` }}
              />
            </div>
          </div>
        </div>
      </div>

      <div className="sr-only">
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
  );
}
