"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Check, X } from "lucide-react";
import {
  DEMO_JD_KEYWORDS,
  DEMO_RESUME_LINES,
  classifyKeywords,
  revealedCount,
} from "@/lib/marketing/keywordScan";
import {
  normalizedPosition,
  shouldAnimate,
} from "@/lib/marketing/spotlight";
import {
  ILLUSTRATIVE_NOTE,
  SECTION,
  SECTION_HEADING,
  SECTION_SUBHEADING,
} from "./styles";

/**
 * Cursor-swept keyword audit, running entirely on local sample data.
 *
 * This never calls `POST /api/checkup`: that endpoint costs two LLM passes and
 * is capped at 12/hour per IP, so driving it from the busiest public page would
 * spend inference budget on idle visitors and exhaust the quota the real tool
 * needs. The invitation to run the real analyzer sits directly below.
 *
 * Every keyword and its verdict is rendered at all times. The sweep only
 * changes emphasis — keywords it has not yet reached are dimmed while the
 * pointer is inside the panel, and never while it is outside. That ordering is
 * what avoids a hydration flicker: the server and the resting client agree that
 * everything is fully visible.
 *
 * Sweep progress is measured against the keyword column, not the full two-column
 * surface, so the line and the dimming stay aligned.
 */
export function KeywordScanDemo() {
  const [animate, setAnimate] = useState(false);
  const [scanning, setScanning] = useState(false);

  const results = useMemo(
    () => classifyKeywords(DEMO_RESUME_LINES.join("\n"), DEMO_JD_KEYWORDS),
    [],
  );
  const matched = results.filter((result) => result.status === "matched").length;

  const [passed, setPassed] = useState(results.length);

  const surfaceRef = useRef<HTMLDivElement>(null);
  const keywordsRef = useRef<HTMLDivElement>(null);
  const frameRef = useRef<number | null>(null);
  const pendingRef = useRef<number | null>(null);

  useEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    const pointer = window.matchMedia("(pointer: fine)");
    const sync = () =>
      setAnimate(
        shouldAnimate({
          prefersReducedMotion: motion.matches,
          hasFinePointer: pointer.matches,
        }),
      );

    sync();
    motion.addEventListener("change", sync);
    pointer.addEventListener("change", sync);
    return () => {
      motion.removeEventListener("change", sync);
      pointer.removeEventListener("change", sync);
    };
  }, []);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLDivElement>) => {
      if (!animate) return;
      const surface = surfaceRef.current;
      const keywords = keywordsRef.current;
      if (!surface || !keywords) return;

      pendingRef.current = event.clientX;

      if (frameRef.current !== null) return;
      frameRef.current = window.requestAnimationFrame(() => {
        frameRef.current = null;
        const clientX = pendingRef.current;
        const node = surfaceRef.current;
        const keywordNode = keywordsRef.current;
        if (clientX === null || !node || !keywordNode) return;

        const surfaceBounds = node.getBoundingClientRect();
        const keywordBounds = keywordNode.getBoundingClientRect();
        if (keywordBounds.width <= 0) return;

        const { x } = normalizedPosition(
          { x: clientX, y: keywordBounds.top },
          {
            left: keywordBounds.left,
            top: keywordBounds.top,
            width: keywordBounds.width,
            height: keywordBounds.height,
          },
        );

        const scanX =
          keywordBounds.left - surfaceBounds.left + x * keywordBounds.width;
        node.style.setProperty("--scan-x", `${scanX}px`);
        const next = revealedCount(x, results.length);
        setPassed((current) => (current === next ? current : next));
      });
    },
    [animate, results.length],
  );

  const handlePointerEnter = useCallback(() => {
    if (animate) setScanning(true);
  }, [animate]);

  const handlePointerLeave = useCallback(() => {
    if (frameRef.current !== null) {
      cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
    }
    pendingRef.current = null;

    setScanning(false);
    setPassed(results.length);
    surfaceRef.current?.style.removeProperty("--scan-x");
  }, [results.length]);

  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>
        This is the keyword audit, before you sign up
      </h2>
      <p className={SECTION_SUBHEADING}>
        Every job description carries must-haves an applicant tracking system
        looks for. TalioCV pulls them out and tells you which ones your
        experience actually backs up.
      </p>

      <div
        ref={surfaceRef}
        onPointerMove={handlePointerMove}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        data-scan-surface
        className="sr-scan-surface relative overflow-hidden rounded-2xl border border-slate-300 dark:border-slate-700 bg-slate-100/60 dark:bg-slate-800/60 p-6 sm:p-8 grid gap-8 md:grid-cols-2"
      >
        <span aria-hidden className="sr-scan-sweep" />

        <div>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3">
            Sample resume
          </h3>
          <ul className="space-y-2">
            {DEMO_RESUME_LINES.map((line) => (
              <li
                key={line}
                className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed"
              >
                {line}
              </li>
            ))}
          </ul>
        </div>

        <div ref={keywordsRef}>
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 mb-3">
            Job description must-haves
          </h3>
          <ul className="flex flex-wrap gap-2">
            {results.map((result, index) => {
              const dimmed = scanning && index >= passed;
              const isMatch = result.status === "matched";
              return (
                <li
                  key={result.term}
                  data-keyword={result.term}
                  data-status={result.status}
                  className={`inline-flex items-center gap-1.5 rounded-lg border px-2.5 py-1 text-xs transition-opacity duration-150 ${
                    dimmed ? "opacity-45" : "opacity-100"
                  } ${
                    isMatch
                      ? "border-emerald-300 dark:border-emerald-700 bg-emerald-50 dark:bg-emerald-900/40 text-emerald-800 dark:text-emerald-200"
                      : "border-rose-300 dark:border-rose-800 bg-rose-50 dark:bg-rose-900/30 text-rose-800 dark:text-rose-200"
                  }`}
                >
                  {isMatch ? (
                    <Check aria-hidden className="w-3.5 h-3.5" />
                  ) : (
                    <X aria-hidden className="w-3.5 h-3.5" />
                  )}
                  {result.term}
                  <span className="sr-only">
                    {isMatch ? " — covered by the resume" : " — missing"}
                  </span>
                </li>
              );
            })}
          </ul>

          <p className="mt-4 text-sm font-semibold text-slate-800 dark:text-slate-200">
            {matched} of {results.length} must-haves covered
          </p>
          <p className="mt-1 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
            The gaps are the point. TalioCV reports what a posting asks for and
            your history does not support, instead of inventing it.
          </p>
        </div>
      </div>

      <p className={`mt-4 text-center ${ILLUSTRATIVE_NOTE}`}>
        Sample resume and job description &mdash; your scan runs on your own.
      </p>
    </section>
  );
}
