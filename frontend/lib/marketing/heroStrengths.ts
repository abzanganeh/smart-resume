/**
 * Rotating hero strength lines — subordinate to the fixed company-watch h1.
 *
 * Every line maps to a shipped capability. Copy lives here (not inline in
 * components) so unit tests can pin claims against real product behavior.
 */

export interface HeroStrength {
  id: string;
  line: string;
}

/** Headline covers company watch; the rotator carries the rest. */
export const HERO_STRENGTHS: readonly HeroStrength[] = [
  {
    id: "story-mode",
    line: "Speak your career out loud — we turn it into a master resume.",
  },
  {
    id: "career-discovery",
    line: "Ten realistic job titles, each scored against your real experience.",
  },
  {
    id: "ats-keywords",
    line:
      "Every must-have keyword pulled from the posting, audited against your evidence.",
  },
  {
    id: "ats-score",
    line: "A before-and-after ATS score, computed in code — never guessed.",
  },
  {
    id: "cover-letters",
    line:
      "Cover letters drawn from the same evidence, so they can never contradict your resume.",
  },
  {
    id: "tracker",
    line: "Every application on one board, from Draft to Offer.",
  },
] as const;
