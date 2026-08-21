import { faqEntries, faqJsonLdScript } from "@/lib/marketing/faq";
import { SECTION, SECTION_HEADING, SECTION_SUBHEADING } from "./styles";

/**
 * Answers are rendered visibly rather than collapsed behind `<details>`.
 *
 * The point of this section is to be quotable by search and answer engines, and
 * content that starts hidden is weighted lower for exactly that. The credit
 * count arrives as a prop so the copy tracks `GET /api/billing/free-tier`
 * instead of hardcoding a number that drifts.
 */
export function FaqSection({ startingCredits }: { startingCredits: number }) {
  const entries = faqEntries(startingCredits);
  const structuredData = faqJsonLdScript(entries);

  return (
    <section className={`${SECTION} pb-24`}>
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{ __html: structuredData }}
      />

      <h2 className={SECTION_HEADING}>Questions people ask first</h2>
      <p className={SECTION_SUBHEADING}>
        Short answers, and nothing the product cannot back up.
      </p>

      <dl className="grid gap-6 md:grid-cols-2">
        {entries.map((entry) => (
          <div
            key={entry.question}
            className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-5"
          >
            <dt className="font-semibold text-sm text-slate-900 dark:text-slate-100 mb-2">
              {entry.question}
            </dt>
            <dd className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {entry.answer}
            </dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
