/**
 * Landing-page journey content.
 *
 * Lives outside the section components so the copy can be unit-tested against
 * what the backend actually gates. `access` is not a marketing choice — it
 * mirrors the router gates, and `tests/lib/marketingJourney.test.ts` pins the
 * two stages whose gating is easy to get wrong.
 */

/**
 * `mixed` means partially usable on the free tier. Job search is the only such
 * stage today: free users with confirmed preferred titles get corpus search,
 * while expanded (Hirebase) search raises 402 in
 * `backend/app/routers/jobs.py::_require_job_search_access`.
 */
export type JourneyAccess = "free" | "mixed" | "paid";

export interface JourneyStep {
  id: string;
  step: number;
  title: string;
  description: string;
  access: JourneyAccess;
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
      "Speak your career out loud, upload an existing resume, or answer a coached interview. TalioCV turns it into a master resume you only build once.",
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
      "TalioCV reads your master resume and suggests ten realistic job titles, each with a fit score and the strengths and gaps behind it. You do not have to know what to search for.",
    access: "free",
    ctaLabel: "See my career options",
    ctaHref: REGISTER,
  },
  {
    id: "jobs",
    step: 3,
    title: "Find opportunities",
    description:
      "Search live roles against your confirmed titles, block companies you are not interested in, and watch specific employers for new openings.",
    access: "mixed",
    accessNote:
      "Corpus search is free once you confirm at least five titles. Expanded search and fit scoring need a paid plan.",
    ctaLabel: "Find jobs for me",
    ctaHref: REGISTER,
  },
  {
    id: "tailor",
    step: 4,
    title: "Make every application fit",
    description:
      "Paste the job description. TalioCV extracts every must-have keyword, audits your resume against it, rewrites from your real experience, and scores the result.",
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
export function journeyBadge(access: JourneyAccess): string | null {
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
