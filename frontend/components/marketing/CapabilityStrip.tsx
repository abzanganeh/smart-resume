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
import { journeyBadge, type JourneyAccess } from "@/lib/marketing/journey";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

/**
 * Compact capability list.
 *
 * Kept as visible `h3`s rather than folded into the collapsed detail section:
 * these are the terms people search for, and burying them inside a closed
 * `<details>` cost the page its heading hierarchy.
 */
const CAPABILITIES: {
  icon: React.ReactNode;
  title: string;
  blurb: string;
  access?: JourneyAccess;
}[] = [
  {
    icon: <Mic className="w-4 h-4 text-indigo-700 dark:text-indigo-400" />,
    title: "Story Mode",
    blurb: "Speak your career, or answer a coached interview.",
  },
  {
    icon: <Layers className="w-4 h-4 text-amber-700 dark:text-amber-400" />,
    title: "Master Resume",
    blurb: "One permanent record every tailored resume draws from.",
  },
  {
    icon: <Sparkles className="w-4 h-4 text-amber-700 dark:text-amber-400" />,
    title: "ATS Optimization",
    blurb: "Keyword extraction, gap audit, and a scored quality check.",
  },
  {
    icon: <FileText className="w-4 h-4 text-sky-700 dark:text-sky-400" />,
    title: "Cover Letters",
    blurb: "Generated from the same evidence as your resume.",
  },
  {
    icon: <Search className="w-4 h-4 text-emerald-700 dark:text-emerald-400" />,
    title: "Job Search",
    blurb: "Search your confirmed titles and block companies you skip.",
    access: "mixed",
  },
  {
    icon: <Star className="w-4 h-4 text-pink-700 dark:text-pink-400" />,
    title: "Job Fit Score",
    blurb: "Check a role against your resume before you invest time.",
    access: "paid",
  },
  {
    icon: <Briefcase className="w-4 h-4 text-orange-700 dark:text-orange-400" />,
    title: "Application Tracker",
    blurb: "Draft through Applied, Interviewing, and Offer.",
  },
  {
    icon: (
      <MessageSquare className="w-4 h-4 text-violet-700 dark:text-violet-400" />
    ),
    title: "AI Chat & Inline Editing",
    blurb: "Per-section regeneration with undo/redo history.",
  },
];

export function CapabilityStrip() {
  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Everything you need to get hired</h2>
      <p className={SECTION_SUBHEADING}>
        One platform instead of a job board, a document editor, and a
        spreadsheet.
      </p>

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {CAPABILITIES.map((item) => {
          const badge = item.access ? journeyBadge(item.access) : null;
          return (
            <div
              key={item.title}
              className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4"
            >
              <div className="flex items-center gap-2 mb-1.5">
                {item.icon}
                <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                  {item.title}
                </h3>
              </div>
              <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
                {item.blurb}
              </p>
              {badge && (
                <span className="inline-block mt-2 text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
                  {badge}
                </span>
              )}
            </div>
          );
        })}
      </div>
    </section>
  );
}
