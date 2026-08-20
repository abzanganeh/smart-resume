import { ChevronRight } from "lucide-react";
import { VOICE_AVAILABILITY_COPY } from "@/lib/freeTier";
import { journeyBadge, type JourneyAccess } from "@/lib/marketing/journey";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

interface DetailPoint {
  text: string;
  /** Defaults to free. Gated capability must say so here, not only in the
   * journey section further up the page. */
  access?: JourneyAccess;
}

interface DetailGroup {
  question: string;
  points: DetailPoint[];
}

const DETAILS: DetailGroup[] = [
  {
    question: "How does TalioCV avoid inventing things about me?",
    points: [
      {
        text: "Every rewrite draws from your master resume, which is the only source of truth for your experience.",
      },
      {
        text: "If a bullet has no metric, the gap is reported for you to fill instead of being filled in for you.",
      },
      {
        text: "An 8-point QA checklist runs before every export, and the ATS score is computed deterministically in the backend — never assigned by a language model.",
      },
      { text: "Job titles, company names, and dates are never rewritten." },
      {
        text: "You see a before and after ATS score, so the improvement is measurable rather than asserted.",
      },
    ],
  },
  {
    question: "What exactly is in the platform?",
    points: [
      {
        text: `Story Mode — speak your career, or answer a coached interview. ${VOICE_AVAILABILITY_COPY}`,
      },
      {
        text: "Master Resume — a permanent semantic store every tailored resume draws from.",
      },
      {
        text: "ATS optimization — four-phase tailoring: keyword extraction, gap audit, evidence-based rewrite, ATS quality check.",
      },
      {
        text: "Cover letters generated from the same evidence as the resume.",
      },
      {
        text: "Job search with company blocking, plus Career Watch for monitoring specific employers.",
        access: "mixed",
      },
      {
        text: "Job Fit Score, comparing your master resume to any job description before you invest time.",
        access: "paid",
      },
      {
        text: "Application tracker from Draft through Applied, Interviewing, and Offer.",
      },
      {
        text: "AI chat and per-section regeneration with undo/redo version history.",
      },
    ],
  },
  {
    question: "Which AI model runs my rewrites?",
    points: [
      {
        text: "Platform AI is included on every plan — there are no API keys to configure.",
      },
      {
        text: "Free through Pro+ use Gemini for rewrites; Premium adds Claude Sonnet for the rewrite phase.",
      },
      { text: "Model quality scales with your subscription tier." },
    ],
  },
];

export function PlatformDetails() {
  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Built on quality rules, not guesswork</h2>
      <p className={SECTION_SUBHEADING}>
        The details, for anyone who wants them.
      </p>

      <div className="max-w-3xl mx-auto space-y-3">
        {DETAILS.map((group) => (
          <details
            key={group.question}
            className="group rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 px-5 py-4"
          >
            <summary className="flex items-center gap-2 cursor-pointer text-sm font-semibold text-slate-900 dark:text-slate-100 list-none marker:content-none [&::-webkit-details-marker]:hidden">
              <ChevronRight
                aria-hidden
                className="w-4 h-4 shrink-0 text-amber-700 dark:text-amber-400 transition-transform group-open:rotate-90"
              />
              {group.question}
            </summary>
            <ul className="mt-3 pl-6 space-y-2 list-disc text-sm text-slate-600 dark:text-slate-400">
              {group.points.map((point) => {
                const badge = point.access ? journeyBadge(point.access) : null;
                return (
                  <li key={point.text} className="leading-relaxed">
                    {point.text}
                    {badge && (
                      <span className="ml-2 whitespace-nowrap text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
                        {badge}
                      </span>
                    )}
                  </li>
                );
              })}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}
