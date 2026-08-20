import { ArrowDown, Check, X } from "lucide-react";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

const WITHOUT = [
  "\u201cI need a job.\u201d",
  "Scroll a job board",
  "Hundreds of listings",
  "Guess which ones fit",
  "Open Word",
  "Rewrite the resume by hand",
  "Apply",
  "Log it in a spreadsheet",
];

const WITH = [
  "Tell your story once",
  "Get the roles you fit",
  "Search those roles",
  "Paste the job description",
  "Tailor and check the ATS score",
  "Apply",
  "Track it automatically",
];

export function ComparisonSection() {
  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Same goal, fewer dead ends</h2>
      <p className={SECTION_SUBHEADING}>
        The hard part of a job search usually is not writing the resume. It is
        deciding what to apply for, over and over.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-5 max-w-3xl mx-auto">
        <div className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-6">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-slate-700 dark:text-slate-300 mb-4">
            <X className="w-4 h-4 text-red-600 dark:text-red-400" />
            On your own
          </h3>
          <ol className="space-y-2">
            {WITHOUT.map((line, index) => (
              <li key={line} className="text-sm text-slate-600 dark:text-slate-400">
                {line}
                {index < WITHOUT.length - 1 && (
                  <ArrowDown
                    aria-hidden
                    className="w-3 h-3 mt-1.5 text-slate-400 dark:text-slate-600"
                  />
                )}
              </li>
            ))}
          </ol>
        </div>

        <div className="rounded-xl border border-emerald-200 dark:border-emerald-700/50 bg-emerald-50/60 dark:bg-emerald-900/20 p-6">
          <h3 className="flex items-center gap-2 text-sm font-semibold text-emerald-800 dark:text-emerald-300 mb-4">
            <Check className="w-4 h-4" />
            With TalioCV
          </h3>
          <ol className="space-y-2">
            {WITH.map((line, index) => (
              <li key={line} className="text-sm text-slate-700 dark:text-slate-300">
                {line}
                {index < WITH.length - 1 && (
                  <ArrowDown
                    aria-hidden
                    className="w-3 h-3 mt-1.5 text-emerald-500/70 dark:text-emerald-600"
                  />
                )}
              </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
