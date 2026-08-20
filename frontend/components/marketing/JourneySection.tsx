import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { JOURNEY_STEPS, journeyBadge } from "@/lib/marketing/journey";
import {
  INLINE_CTA,
  SECTION,
  SECTION_HEADING,
  SECTION_SUBHEADING,
} from "./styles";

export function JourneySection() {
  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Your job search, step by step</h2>
      <p className={SECTION_SUBHEADING}>
        Six stages, one place. Badges show exactly where a paid plan is required
        &mdash; everything else works on the free tier.
      </p>

      <ol className="space-y-4">
        {JOURNEY_STEPS.map((step) => {
          const badge = journeyBadge(step.access);
          return (
            <li
              key={step.id}
              className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-5 sm:p-6 flex flex-col sm:flex-row gap-4 sm:gap-6"
            >
              <span
                aria-hidden
                className="shrink-0 font-mono text-sm font-bold text-amber-700 dark:text-amber-400"
              >
                {String(step.step).padStart(2, "0")}
              </span>
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2 mb-1.5">
                  <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                    {step.title}
                  </h3>
                  {badge && (
                    <span className="text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
                      {badge}
                    </span>
                  )}
                </div>
                <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                  {step.description}
                </p>
                {step.accessNote && (
                  <p className="mt-2 text-xs text-slate-500 dark:text-slate-500">
                    {step.accessNote}
                  </p>
                )}
                <Link href={step.ctaHref} className={`${INLINE_CTA} mt-3`}>
                  {step.ctaLabel}
                  <ArrowRight className="w-4 h-4" />
                </Link>
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
