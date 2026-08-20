import { ChevronRight } from "lucide-react";
import { VOICE_AVAILABILITY_COPY } from "@/lib/freeTier";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

interface DetailGroup {
  question: string;
  points: string[];
}

const DETAILS: DetailGroup[] = [
  {
    question: "How does TalioCV avoid inventing things about me?",
    points: [
      "Every rewrite draws from your master resume, which is the only source of truth for your experience.",
      "If a bullet has no metric, the gap is reported for you to fill instead of being filled in for you.",
      "An 8-point QA checklist runs before every export, and the ATS score is computed deterministically in the backend — never assigned by a language model.",
      "Job titles, company names, and dates are never rewritten.",
      "You see a before and after ATS score, so the improvement is measurable rather than asserted.",
    ],
  },
  {
    question: "What exactly is in the platform?",
    points: [
      `Story Mode — speak your career, or answer a coached interview. ${VOICE_AVAILABILITY_COPY}`,
      "Master Resume — a permanent semantic store every tailored resume draws from.",
      "Four-phase tailoring — keyword extraction, gap audit, evidence-based rewrite, ATS quality check.",
      "Cover letters generated from the same evidence as the resume.",
      "Job search with company blocking, plus Career Watch for monitoring specific employers.",
      "Job Fit Score, comparing your master resume to any job description before you invest time.",
      "Application tracker from Draft through Applied, Interviewing, and Offer.",
      "AI chat and per-section regeneration with undo/redo version history.",
    ],
  },
  {
    question: "Which AI model runs my rewrites?",
    points: [
      "Platform AI is included on every plan — there are no API keys to configure.",
      "Free through Pro+ use Gemini for rewrites; Premium adds Claude Sonnet for the rewrite phase.",
      "Model quality scales with your subscription tier.",
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
            <summary className="flex items-center gap-2 cursor-pointer text-sm font-semibold text-slate-900 dark:text-slate-100 marker:content-none">
              <ChevronRight
                aria-hidden
                className="w-4 h-4 shrink-0 text-amber-700 dark:text-amber-400 transition-transform group-open:rotate-90"
              />
              {group.question}
            </summary>
            <ul className="mt-3 pl-6 space-y-2 list-disc text-sm text-slate-600 dark:text-slate-400">
              {group.points.map((point) => (
                <li key={point} className="leading-relaxed">
                  {point}
                </li>
              ))}
            </ul>
          </details>
        ))}
      </div>
    </section>
  );
}
