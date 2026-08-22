/**
 * Capability copy for the landing page spotlight.
 *
 * Deliberately icon-free so the model stays a pure, unit-testable module: the
 * component owns the id → icon mapping. `access` is reused from the journey
 * model rather than redeclared, so gating has exactly one source of truth
 * across the journey, the spotlight, and the detail disclosure.
 */

import type { FeatureAccess } from "./journey";

export interface Capability {
  id: string;
  title: string;
  /** One line, always rendered — never hidden behind hover. */
  blurb: string;
  /** Expanded copy rendered in every card — always visible, not hover-gated. */
  detail: string;
  access?: FeatureAccess;
}

export const CAPABILITIES: readonly Capability[] = [
  {
    id: "story",
    title: "Story Mode",
    blurb: "Speak your career, or answer a coached interview.",
    detail:
      "Record your history out loud, upload a resume you already have, or work through up to fifteen structured career questions. Whichever you pick becomes structured experience the rest of the product reuses.",
  },
  {
    id: "master-resume",
    title: "Master Resume",
    blurb: "One permanent record every tailored resume draws from.",
    detail:
      "Your master resume is the single source every tailored version is generated from, so you never rewrite your history for a new application — you only ever add to it.",
  },
  {
    id: "ats",
    title: "ATS Optimization",
    blurb: "Keyword extraction, gap audit, and a scored quality check.",
    detail:
      "Every must-have keyword is pulled from the job description and audited against your evidence. The resulting score is computed in code, not guessed by a language model, so the same resume always scores the same.",
  },
  {
    id: "cover-letters",
    title: "Cover Letters",
    blurb: "Generated from the same evidence as your resume.",
    detail:
      "Cover letters draw on the same structured experience as your resume, so the two can never contradict each other. One credit per letter on the free plan.",
  },
  {
    id: "job-search",
    title: "Job Search",
    blurb: "Search your confirmed titles and block companies you skip.",
    detail:
      "Search live roles against the titles you confirmed, and permanently block employers you have no interest in. Corpus search is free once you confirm titles; expanded search needs a paid plan.",
    access: "mixed",
  },
  {
    id: "fit-score",
    title: "Job Fit Score",
    blurb: "Check a role against your resume before you invest time.",
    detail:
      "Score a specific posting against your master resume, with the strengths and gaps behind the number, before you spend a credit tailoring for it.",
    access: "paid",
  },
  {
    id: "tracker",
    title: "Application Tracker",
    blurb: "Draft through Applied, Interviewing, and Offer.",
    detail:
      "Every application lands on a board with notes and status history, so a role that has gone quiet stays visible instead of being forgotten.",
  },
  {
    id: "ai-chat",
    title: "AI Chat & Inline Editing",
    blurb: "Per-section regeneration with undo/redo history.",
    detail:
      "Regenerate any single section without disturbing the rest, then step backwards and forwards through every revision until the wording is yours.",
  },
];

export function capabilityById(id: string): Capability {
  const capability = CAPABILITIES.find((candidate) => candidate.id === id);
  if (!capability) {
    throw new Error(`Unknown capability: ${id}`);
  }
  return capability;
}
