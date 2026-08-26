/**
 * Full hero message sets for the landing rotator.
 *
 * Each set focuses on one shipped capability. All variants stay in the DOM for
 * crawlers and assistive tech; scroll position drives which set is visible.
 */

import { PRODUCT_NAME } from "@/lib/brand";

export interface HeroMessage {
  id: string;
  badge: string;
  headlineLead: string;
  headlineAccent: string;
  tagline: string;
  description: string;
}

export const HERO_MESSAGES: readonly HeroMessage[] = [
  {
    id: "company-watch",
    badge: "Company watch · Alerts in minutes · Never fabricates metrics",
    headlineLead: "Name the companies.",
    headlineAccent: "We'll tell you the minute they're hiring.",
    tagline: "Your short list, on your schedule — not a job board's.",
    description: `${PRODUCT_NAME} watches the careers pages you pick — the company's own listings, not a job board — and tells you when a role opens, in minutes rather than days. Then it tailors an ATS-optimized resume to it, using only your real experience.`,
  },
  {
    id: "story-mode",
    badge: "Story Mode · Master resume · Built once",
    headlineLead: "Speak your career out loud.",
    headlineAccent: "We turn it into a master resume.",
    tagline: "Upload, coach, or interview — one source of truth for every application.",
    description: `Tell ${PRODUCT_NAME} your story in your own words. It structures a master resume you refine once, then reuse for every role — no copy-paste drift between versions.`,
  },
  {
    id: "career-discovery",
    badge: "Career discovery · Fit scoring · Realistic titles",
    headlineLead: "Ten realistic job titles.",
    headlineAccent: "Each scored against your real experience.",
    tagline: "You do not have to know what to search for on day one.",
    description: `${PRODUCT_NAME} reads your master resume and suggests titles that actually fit — with strengths, gaps, and a fit score behind each one.`,
  },
  {
    id: "ats-keywords",
    badge: "ATS optimization · Keyword audit · Evidence-backed",
    headlineLead: "Every must-have keyword",
    headlineAccent: "pulled from the posting and checked against your evidence.",
    tagline: "Tailoring that stays honest — nothing invented to pass a scan.",
    description: `Paste a job description. ${PRODUCT_NAME} extracts what the ATS expects, audits your resume against it, and rewrites from experience you already have.`,
  },
  {
    id: "ats-score",
    badge: "Deterministic scoring · Before & after · No guesswork",
    headlineLead: "A before-and-after ATS score,",
    headlineAccent: "computed in code — never guessed.",
    tagline: "See exactly what changed and why the score moved.",
    description: `${PRODUCT_NAME} runs the same scoring engine on every version so you can compare drafts with numbers you can trust — not a model's hunch.`,
  },
  {
    id: "cover-letters",
    badge: "Cover letters · Same evidence · No contradictions",
    headlineLead: "Cover letters drawn from the same evidence",
    headlineAccent: "so they never contradict your resume.",
    tagline: "One story, every document — tailored per role.",
    description: `When ${PRODUCT_NAME} drafts a cover letter, it pulls from the same master resume and job audit — so every claim matches what you already submitted.`,
  },
  {
    id: "tracker",
    badge: "Application tracker · Draft to Offer · One board",
    headlineLead: "Every application on one board,",
    headlineAccent: "from Draft to Offer.",
    tagline: "Status, notes, and next steps without a spreadsheet.",
    description: `Track where you applied, what stage each role is in, and what to do next — inside ${PRODUCT_NAME}, next to the resumes and cover letters you already built.`,
  },
] as const;
