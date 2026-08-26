"use client";

import { useEffect, useRef } from "react";
import { ChevronRight } from "lucide-react";
import { accessBadge } from "@/lib/marketing/journey";
import { faqEntries } from "@/lib/marketing/faq";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

/**
 * One collapsible FAQ block. Answers stay in the HTML whether open or closed.
 * At most one question is open at a time; open entries collapse when the
 * section scrolls out of view.
 */
export function FaqSection({ startingCredits }: { startingCredits: number }) {
  const entries = faqEntries(startingCredits);
  const sectionRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const section = sectionRef.current;
    if (!section) return;

    const onToggle = (event: Event) => {
      const target = event.target;
      if (!(target instanceof HTMLDetailsElement) || !target.open) return;
      section.querySelectorAll("details").forEach((details) => {
        if (details !== target) details.open = false;
      });
    };

    section.addEventListener("toggle", onToggle);

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) return;
        section
          .querySelectorAll<HTMLDetailsElement>("details[open]")
          .forEach((details) => {
            details.open = false;
          });
      },
      { threshold: 0 },
    );

    observer.observe(section);
    return () => {
      section.removeEventListener("toggle", onToggle);
      observer.disconnect();
    };
  }, []);

  return (
    <section ref={sectionRef} id="faq" className={`${SECTION} scroll-mt-24 pb-24`}>
      <h2 className={SECTION_HEADING}>Questions people ask first</h2>
      <p className={SECTION_SUBHEADING}>
        Short answers, and nothing the product cannot back up.
      </p>

      <div className="mx-auto max-w-3xl space-y-3">
        {entries.map((entry) => (
          <details
            key={entry.question}
            name="landing-faq"
            className="group rounded-xl border border-slate-300 bg-slate-100/40 px-5 py-4 dark:border-slate-700 dark:bg-slate-800/40"
          >
            <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-semibold text-slate-900 marker:content-none dark:text-slate-100 [&::-webkit-details-marker]:hidden">
              <ChevronRight
                aria-hidden
                className="h-4 w-4 shrink-0 text-amber-700 transition-transform group-open:rotate-90 dark:text-amber-400"
              />
              {entry.question}
            </summary>
            {entry.points ? (
              <ul className="mt-3 list-disc space-y-2 pl-6 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {entry.points.map((point) => {
                  const badge = point.access ? accessBadge(point.access) : null;
                  return (
                    <li key={point.text}>
                      {point.text}
                      {badge && (
                        <span className="ml-2 whitespace-nowrap rounded border border-emerald-200 bg-emerald-50 px-1.5 py-0.5 text-[10px] font-bold text-emerald-700 dark:border-emerald-700 dark:bg-emerald-900/60 dark:text-emerald-300">
                          {badge}
                        </span>
                      )}
                    </li>
                  );
                })}
              </ul>
            ) : (
              <p className="mt-3 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
                {entry.answer}
              </p>
            )}
          </details>
        ))}
      </div>
    </section>
  );
}
