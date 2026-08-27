/**
 * Landing-page journey content and the shared feature-gating vocabulary.
 *
 * Lives outside the section components so the copy can be unit-tested against
 * what the backend actually gates. `access` is not a marketing choice — it
 * mirrors the router gates, and `tests/lib/marketingJourney.test.ts` pins the
 * two stages whose gating is easy to get wrong.
 *
 * `FeatureAccess` and `accessBadge` are reused by the capability strip and the
 * detail disclosure so gating can never drift between the places we state it.
 */

import { COMPANY_LINE, FLINT_DESKTOP_URL, FLINT_PRODUCT_NAME, PRODUCT_NAME } from "@/lib/brand";

/**
 * `mixed` means partially usable on the free tier. Job search is the only such
 * stage today: free users with confirmed preferred titles get corpus search,
 * while expanded (Hirebase) search raises 402 in
 * `backend/app/routers/jobs.py::_require_job_search_access`.
 */
export type FeatureAccess = "free" | "mixed" | "paid";

export interface JourneyStep {
  id: string;
  step: number;
  title: string;
  description: string;
  access: FeatureAccess;
  /** Shown under the description when free-tier limits need spelling out. */
  accessNote?: string;
  ctaLabel: string;
  ctaHref: string;
}

const REGISTER = "/auth?mode=register";

export const JOURNEY_STEPS: readonly JourneyStep[] = [
  {
    id: "story",
    step: 1,
    title: "Build your master resume",
    description:
      `Speak your career out loud, upload an existing resume, or answer a coached interview. ${PRODUCT_NAME} turns it into a master resume you only build once.`,
    access: "free",
    accessNote: "Story coaching and rewrites spend signup credits.",
    ctaLabel: "Start your career story",
    ctaHref: REGISTER,
  },
  {
    id: "discover",
    step: 2,
    title: "Choose roles to search for",
    description:
      `${PRODUCT_NAME} reads your master resume and suggests ten realistic job titles, each with a fit score and the strengths and gaps behind it. Pick the ones you want — or add your own — up to twelve roles.`,
    access: "free",
    ctaLabel: "See my career options",
    ctaHref: REGISTER,
  },
  {
    id: "jobs",
    step: 3,
    title: "Search jobs",
    description:
      `Search our company job corpus with your target roles. ${PRODUCT_NAME} surfaces real openings from hundreds of tech employers — and Career Watch can alert you when a company you follow posts a new role.`,
    access: "mixed",
    accessNote:
      "Free plans watch one company every 30 minutes and search the corpus once you confirm your target job titles. Paid plans watch more companies, check more often, and add expanded search and fit scoring.",
    ctaLabel: "Search the job corpus",
    ctaHref: REGISTER,
  },
  {
    id: "capture",
    step: 4,
    title: "Capture a job posting",
    description:
      `On Greenhouse, Lever, Ashby, and similar sites, the ${PRODUCT_NAME} browser extension captures the full job description in one click — no copy-paste. You can also save a posting from in-app search.`,
    access: "free",
    ctaLabel: "See how capture works",
    ctaHref: REGISTER,
  },
  {
    id: "tailor",
    step: 5,
    title: "Tailor your resume",
    description:
      `Paste a job description or send one from the extension. ${PRODUCT_NAME} extracts every must-have keyword, audits your resume against it, rewrites from your real experience, and scores the result.`,
    access: "free",
    accessNote: "One credit per tailored resume on the free plan.",
    ctaLabel: "Check my resume free",
    ctaHref: "/checkup",
  },
  {
    id: "apply",
    step: 6,
    title: "Apply with autofill",
    description:
      `Return to the employer site with the ${PRODUCT_NAME} extension and autofill application forms from your tailored resume. Export a clean PDF or DOCX and generate a matching cover letter from the same evidence when you are ready to submit.`,
    access: "free",
    accessNote: "Autofill is free. One credit per cover letter on the free plan.",
    ctaLabel: "Start applying faster",
    ctaHref: REGISTER,
  },
  {
    id: "track",
    step: 7,
    title: "Track applications",
    description:
      "Every application lands on a board from Draft through Applied, Interviewing, and Offer, with notes and status history so nothing goes quiet unnoticed.",
    access: "free",
    ctaLabel: "Track my applications",
    ctaHref: REGISTER,
  },
];

/** Badge text for a stage, or `null` when the stage is fully free. */
export function accessBadge(access: FeatureAccess): string | null {
  switch (access) {
    case "free":
      return null;
    case "mixed":
      return "Free · expanded on paid";
    case "paid":
      return "Paid plans";
  }
}

export function journeyStepById(id: string): JourneyStep {
  const step = JOURNEY_STEPS.find((candidate) => candidate.id === id);
  if (!step) {
    throw new Error(`Unknown journey step: ${id}`);
  }
  return step;
}

/** Flint desktop co-pilot — separate product, shown below the numbered journey. */
export const FLINT_COMING_SOON = {
  productName: FLINT_PRODUCT_NAME,
  description:
    `Live interview co-pilot — a separate desktop app ${COMPANY_LINE}. Not included in your ${PRODUCT_NAME} subscription. Early access handoff is available from tailored sessions.`,
  learnMoreUrl: FLINT_DESKTOP_URL,
} as const;
