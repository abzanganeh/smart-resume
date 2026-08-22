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

import { PRODUCT_NAME } from "@/lib/brand";

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
    title: "Tell your story",
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
    title: "Discover where you fit",
    description:
      `${PRODUCT_NAME} reads your master resume and suggests ten realistic job titles, each with a fit score and the strengths and gaps behind it. You do not have to know what to search for.`,
    access: "free",
    ctaLabel: "See my career options",
    ctaHref: REGISTER,
  },
  {
    id: "jobs",
    step: 3,
    title: "Watch the companies you want",
    description:
      `Name the employers you care about. ${PRODUCT_NAME} reads their careers pages directly, every 15 to 45 minutes, and tells you when a role opens — usually before it reaches the big job boards. Search the wider corpus any time.`,
    access: "mixed",
    accessNote:
      "Free plans watch one company every 30 minutes and search the corpus once you confirm five titles. Paid plans watch more companies, check more often, and add expanded search and fit scoring.",
    ctaLabel: "Watch a company",
    ctaHref: REGISTER,
  },
  {
    id: "tailor",
    step: 4,
    title: "Make every application fit",
    description:
      `Paste the job description. ${PRODUCT_NAME} extracts every must-have keyword, audits your resume against it, rewrites from your real experience, and scores the result.`,
    access: "free",
    accessNote: "One credit per tailored resume on the free plan.",
    ctaLabel: "Check my resume free",
    ctaHref: "/checkup",
  },
  {
    id: "apply",
    step: 5,
    title: "Apply without the busywork",
    description:
      "Export a clean PDF or DOCX, generate a matching cover letter from the same evidence, and send the application the same day.",
    access: "free",
    accessNote: "One credit per cover letter on the free plan.",
    ctaLabel: "Export and apply",
    ctaHref: REGISTER,
  },
  {
    id: "track",
    step: 6,
    title: "Keep moving",
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
