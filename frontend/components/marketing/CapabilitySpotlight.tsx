"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  Briefcase,
  FileText,
  Layers,
  MessageSquare,
  Mic,
  Search,
  Sparkles,
  Star,
} from "lucide-react";
import { CAPABILITIES } from "@/lib/marketing/capabilities";
import { accessBadge } from "@/lib/marketing/journey";
import {
  nearestIndex,
  shouldAnimate,
  tiltFor,
  type SpotlightRect,
} from "@/lib/marketing/spotlight";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

/**
 * Capability grid with a cursor-following spotlight.
 *
 * The pointer layer is **presentational only**. Every card renders its title,
 * blurb, and detail statically, so the section is complete with no pointer, no
 * JavaScript, and no hover — which is what keeps it readable to crawlers and to
 * assistive technology. Consequently the cards are plain list items rather than
 * buttons: an `<h3>` inside a `<button>` is invalid content model and flattens
 * the accessible name, and a focusable `<div role="button">` wrapping a heading
 * is the same mistake with extra steps. Nothing is conveyed by hover alone, so
 * there is no keyboard equivalent to owe anyone.
 *
 * Pointer coordinates never enter React state. A single listener writes CSS
 * custom properties inside one `requestAnimationFrame`; React re-renders only
 * when the emphasised card changes.
 */

const ICONS: Record<string, React.ReactNode> = {
  story: <Mic aria-hidden className="w-4 h-4 text-indigo-700 dark:text-indigo-400" />,
  "master-resume": (
    <Layers aria-hidden className="w-4 h-4 text-amber-700 dark:text-amber-400" />
  ),
  ats: <Sparkles aria-hidden className="w-4 h-4 text-amber-700 dark:text-amber-400" />,
  "cover-letters": (
    <FileText aria-hidden className="w-4 h-4 text-sky-700 dark:text-sky-400" />
  ),
  "job-search": (
    <Search aria-hidden className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />
  ),
  "fit-score": <Star aria-hidden className="w-4 h-4 text-pink-700 dark:text-pink-400" />,
  tracker: (
    <Briefcase aria-hidden className="w-4 h-4 text-orange-700 dark:text-orange-400" />
  ),
  "ai-chat": (
    <MessageSquare aria-hidden className="w-4 h-4 text-violet-700 dark:text-violet-400" />
  ),
};

const MAX_TILT_DEG = 5;

export function CapabilitySpotlight() {
  const [activeIndex, setActiveIndex] = useState<number | null>(null);
  const [animate, setAnimate] = useState(false);

  const panelRef = useRef<HTMLUListElement>(null);
  const cardRefs = useRef<(HTMLLIElement | null)[]>([]);
  const layoutRef = useRef<SpotlightRect[]>([]);
  const frameRef = useRef<number | null>(null);
  const pendingRef = useRef<{ x: number; y: number } | null>(null);

  // Only attach pointer behaviour for a fine pointer with motion allowed. Touch
  // has no hover to follow, and a reduced-motion request is honoured by never
  // setting the custom properties in the first place — the stylesheet also
  // neutralises the transform, so both layers agree.
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

  /**
   * Cache card geometry relative to the panel. `offsetLeft`/`offsetTop` are
   * layout values: unaffected by the tilt transform (so measuring cannot feed
   * back into itself) and unaffected by scrolling (so the cache stays valid
   * without a scroll listener).
   */
  const measure = useCallback(() => {
    layoutRef.current = cardRefs.current.map((card) =>
      card
        ? {
            left: card.offsetLeft,
            top: card.offsetTop,
            width: card.offsetWidth,
            height: card.offsetHeight,
          }
        : { left: 0, top: 0, width: 0, height: 0 },
    );
  }, []);

  useEffect(() => {
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  useEffect(
    () => () => {
      if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
    },
    [],
  );

  const handlePointerMove = useCallback(
    (event: React.PointerEvent<HTMLUListElement>) => {
      if (!animate) return;
      const panel = panelRef.current;
      if (!panel) return;

      const bounds = panel.getBoundingClientRect();
      pendingRef.current = {
        x: event.clientX - bounds.left,
        y: event.clientY - bounds.top,
      };

      if (frameRef.current !== null) return;
      frameRef.current = window.requestAnimationFrame(() => {
        frameRef.current = null;
        const point = pendingRef.current;
        const node = panelRef.current;
        if (!point || !node) return;

        node.style.setProperty("--spot-x", `${point.x}px`);
        node.style.setProperty("--spot-y", `${point.y}px`);

        const index = nearestIndex(point, layoutRef.current);
        if (index === null) return;

        const tilt = tiltFor(point, layoutRef.current[index], MAX_TILT_DEG);
        node.style.setProperty("--tilt-x", `${tilt.rotateX}deg`);
        node.style.setProperty("--tilt-y", `${tilt.rotateY}deg`);
        setActiveIndex((current) => (current === index ? current : index));
      });
    },
    [animate],
  );

  const handlePointerEnter = useCallback(() => {
    if (animate) measure();
  }, [animate, measure]);

  const handlePointerLeave = useCallback(() => {
    const node = panelRef.current;
    if (node) {
      node.style.removeProperty("--tilt-x");
      node.style.removeProperty("--tilt-y");
    }
    setActiveIndex(null);
  }, []);

  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Everything you need to get hired</h2>
      <p className={SECTION_SUBHEADING}>
        One platform instead of a job board, a document editor, and a
        spreadsheet.
      </p>

      <ul
        ref={panelRef}
        onPointerMove={handlePointerMove}
        onPointerEnter={handlePointerEnter}
        onPointerLeave={handlePointerLeave}
        data-spotlight-panel
        className="sr-spotlight-panel relative grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4"
      >
        <span aria-hidden className="sr-spotlight" />

        {CAPABILITIES.map((capability, index) => {
          const badge = capability.access ? accessBadge(capability.access) : null;
          const isActive = animate && activeIndex === index;

          return (
            <li
              key={capability.id}
              ref={(node) => {
                cardRefs.current[index] = node;
              }}
              data-capability={capability.id}
              data-active={isActive ? "true" : "false"}
              className="sr-spotlight-card relative rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4 data-[active=true]:border-amber-400/70 dark:data-[active=true]:border-amber-400/60"
            >
              <div className="flex items-center gap-2 mb-1.5">
                {ICONS[capability.id]}
                <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                  {capability.title}
                </h3>
              </div>
              <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                {capability.blurb}
              </p>
              <p className="mt-2 text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                {capability.detail}
              </p>
              {badge && (
                <span className="inline-block mt-2 text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
                  {badge}
                </span>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
