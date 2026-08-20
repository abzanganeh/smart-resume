import Link from "next/link";
import { ArrowRight, Compass } from "lucide-react";
import { titleFitBar, titleFitLabel } from "@/lib/jobs";
import { ILLUSTRATIVE_NOTE, INLINE_CTA, SECTION } from "./styles";

/**
 * Illustrative only. Real suggestions come from
 * `GET /api/jobs/title-suggestions`, which derives titles and fit scores from
 * the user's own master resume. Nothing here is a claim about a real person,
 * employer, or score — the visible caption says so.
 */
const EXAMPLE_TITLES = [
  { title: "Backend Engineer", score: 92 },
  { title: "Platform Engineer", score: 86 },
  { title: "Data Engineer", score: 79 },
  { title: "Solutions Engineer", score: 71 },
] as const;

export function CareerDiscoverySection() {
  return (
    <section className={`${SECTION} pb-24`}>
      <div className="text-center max-w-2xl mx-auto mb-10">
        <div className="inline-flex items-center gap-2 rounded-full bg-emerald-50 dark:bg-emerald-900/30 border border-emerald-200 dark:border-emerald-700/50 px-4 py-1.5 text-sm text-emerald-800 dark:text-emerald-300 mb-5">
          <Compass className="w-4 h-4" />
          Included on the free plan
        </div>
        <h2 className="text-3xl font-bold tracking-tight mb-4 text-slate-900 dark:text-white">
          You don&rsquo;t have to know what to search for.
        </h2>
        <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
          Once your master resume exists, TalioCV reads it and proposes ten
          realistic job titles &mdash; each with a fit score and the specific
          strengths and gaps behind that score. Confirm the ones you want and
          they become your search.
        </p>
      </div>

      <div className="max-w-2xl mx-auto rounded-2xl border border-slate-300 dark:border-slate-700 bg-slate-100/60 dark:bg-slate-800/60 p-6 sm:p-8">
        <div className="flex items-baseline justify-between gap-4 mb-5">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Suggested roles
          </h3>
          <span className={ILLUSTRATIVE_NOTE}>
            Illustrative example &mdash; your titles come from your own resume
          </span>
        </div>

        <ul className="space-y-3">
          {EXAMPLE_TITLES.map((role) => (
            <li
              key={role.title}
              className="flex flex-col sm:flex-row sm:items-center gap-1 sm:gap-4"
            >
              <span className="text-sm text-slate-900 dark:text-slate-100 font-medium sm:w-48 shrink-0">
                {role.title}
              </span>
              <span
                aria-hidden
                className="font-mono text-xs text-amber-700 dark:text-amber-400 tracking-tighter"
              >
                {titleFitBar(role.score, 16)}
              </span>
              <span className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">
                {titleFitLabel(role.score)}
              </span>
            </li>
          ))}
          <li className="text-xs text-slate-500 dark:text-slate-500 pt-1">
            …and six more, ranked by fit.
          </li>
        </ul>

        <div className="mt-6 pt-5 border-t border-slate-300 dark:border-slate-700">
          <Link href="/auth?mode=register" className={INLINE_CTA}>
            Discover my career options
            <ArrowRight className="w-4 h-4" />
          </Link>
        </div>
      </div>
    </section>
  );
}
