/**
 * Landing-page FAQ content and its `FAQPage` structured data.
 *
 * Question-and-answer prose is the shape generative search engines quote most
 * readily, which is the point of shipping it. That makes accuracy load-bearing:
 * every answer here has to be checkable against the product.
 *
 * Two rules this module exists to enforce:
 *   - The free-credit count is a parameter, not a literal. It comes from
 *     `GET /api/billing/free-tier`, and hardcoding it here would drift the
 *     moment the backend seed changes.
 *   - No claim about model training. `app/legal/privacy` makes no such claim,
 *     so the marketing page must not invent one.
 */

import { PRODUCT_NAME } from "@/lib/brand";
import { VOICE_AVAILABILITY_COPY } from "@/lib/freeTier";
import { type FeatureAccess } from "@/lib/marketing/journey";

export interface FaqPoint {
  text: string;
  /** Defaults to free. Gated capability must say so here, not only in the journey. */
  access?: FeatureAccess;
}

export interface FaqEntry {
  question: string;
  /** Plain-text answer for JSON-LD and no-JS visibility inside `<details>`. */
  answer: string;
  /** Optional bullet list rendered when the entry is expanded. */
  points?: FaqPoint[];
}

function entryFromPoints(
  question: string,
  points: FaqPoint[],
): FaqEntry {
  return {
    question,
    answer: points.map((point) => point.text).join(" "),
    points,
  };
}

export function faqEntries(startingCredits: number): FaqEntry[] {
  const creditWord = startingCredits === 1 ? "credit" : "credits";

  return [
    {
      question: "Do I need an account to check my resume?",
      answer:
        "No. The resume checkup runs the real analyzer with no account and no card — paste a resume and a job description and you get the same keyword audit the product uses internally.",
    },
    {
      question: "What is an ATS, and why does it matter?",
      answer:
        "An applicant tracking system is the software most employers use to store and filter applications. It reads your resume as text, so wording that does not reflect the job description can keep a qualified application from ever reaching a person.",
    },
    {
      question: `Does ${PRODUCT_NAME} invent achievements to make me look better?`,
      answer:
        "Never. Every rewrite is drawn from experience you supplied, and the quality score is computed in code rather than produced by a language model, so the same resume always scores the same. When a job description asks for something you have not done, it is reported as a gap instead of being invented.",
    },
    entryFromPoints(`How does ${PRODUCT_NAME} avoid inventing things about me?`, [
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
    ]),
    entryFromPoints("How does voice input work?", [
      {
        text: `Story Mode lets you speak your career instead of typing it, or answer a coached interview where the AI asks the questions. ${VOICE_AVAILABILITY_COPY}`,
      },
      {
        text: "Every segment is transcribed into your master resume, which you can edit before anything is used for tailoring.",
      },
    ]),
    entryFromPoints("Which AI model runs my rewrites?", [
      {
        text: "Platform AI is included on every plan — there are no API keys to configure.",
      },
      {
        text: "Every plan uses the same rewrite quality; tiers differ by how many resumes, searches, and watched companies you can run — not by which model rewrites your bullets.",
      },
    ]),
    {
      question: "What does the free plan include?",
      answer: `Registering grants ${startingCredits} AI ${creditWord}, which cover actions like tailoring a resume or writing a cover letter. Career discovery, your master resume, and the application tracker are not credit-gated.`,
    },
    {
      question: "Which features need a paid plan?",
      answer:
        "Expanded job search and fit scoring are subscription-only; every badge on this page says which tier a feature belongs to. Corpus job search is free once you confirm the titles you want.",
    },
    {
      question: "How do I delete my account and my data?",
      answer:
        "Closing your account soft-deletes it with a 30-day grace period, after which backups are purged within 60 days. The privacy policy documents each retention window.",
    },
  ];
}

/**
 * Build schema.org `FAQPage` markup.
 *
 * Throws on a blank question or answer rather than emitting the entry: FAQ
 * structured data with empty fields is read as a spam signal, so failing the
 * build is strictly better than shipping it.
 */
export function faqJsonLd(entries: readonly FaqEntry[]): Record<string, unknown> {
  return {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: entries.map((entry, index) => {
      const question = entry.question.trim();
      const answer = entry.answer.trim();
      if (!question) {
        throw new Error(`FAQ entry ${index} has an empty question`);
      }
      if (!answer) {
        throw new Error(`FAQ entry ${index} has an empty answer`);
      }
      return {
        "@type": "Question",
        name: question,
        acceptedAnswer: { "@type": "Answer", text: answer },
      };
    }),
  };
}

/** Safe string for inline `<script type="application/ld+json">` injection. */
export function faqJsonLdScript(entries: readonly FaqEntry[]): string {
  return JSON.stringify(faqJsonLd(entries)).replace(/</g, "\\u003c");
}
