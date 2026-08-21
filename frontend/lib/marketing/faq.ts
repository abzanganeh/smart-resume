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

export interface FaqEntry {
  question: string;
  answer: string;
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
      question: "Does TalioCV invent achievements to make me look better?",
      answer:
        "Never. Every rewrite is drawn from experience you supplied, and the quality score is computed in code rather than produced by a language model, so the same resume always scores the same. When a job description asks for something you have not done, it is reported as a gap instead of being invented.",
    },
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
