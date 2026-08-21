/**
 * Keyword matching for the hero scan demo.
 *
 * This runs entirely in the browser against the sample data below. It never
 * calls `POST /api/checkup`: that endpoint is rate-limited to 12/hour per IP
 * and runs two LLM passes per call, so driving it from the landing page would
 * spend inference budget on idle visitors and exhaust the quota the real
 * `/checkup` tool needs.
 *
 * Matching is whole-token rather than substring. A demo that counted "Java" as
 * present because the resume said "JavaScript" would overstate coverage, and
 * the page it appears on promises never to fabricate.
 */

export type KeywordStatus = "matched" | "missing";

export interface ScanKeyword {
  term: string;
  status: KeywordStatus;
}

/**
 * Illustrative sample resume. Invented, so the UI labels it as such, and it
 * names no real employer — implying a relationship that does not exist would
 * break the same no-fabrication rule.
 */
export const DEMO_RESUME_LINES: readonly string[] = [
  "Senior Backend Engineer — SaaS platform team",
  "Built and shipped Python services backed by PostgreSQL.",
  "Owned CI/CD pipelines, on-call rotation, and incident response.",
  "Mentored engineers and ran architecture reviews.",
];

/** Sample must-haves, mixing terms the resume covers with ones it does not. */
export const DEMO_JD_KEYWORDS: readonly string[] = [
  "Python",
  "PostgreSQL",
  "CI/CD",
  "incident response",
  "Kubernetes",
  "Terraform",
  "gRPC",
];

const WORD_CHARACTER = /[a-z0-9]/i;

const isWordCharacter = (character: string): boolean =>
  character.length > 0 && WORD_CHARACTER.test(character);

/**
 * Substring search that requires non-word characters (or a string edge) on both
 * sides of the match.
 *
 * Written as an index scan rather than a regex with lookbehind: lookbehind is
 * unsupported in Safari before 16.4, and this runs on a public marketing page
 * where a thrown `SyntaxError` would blank the section.
 */
function containsToken(haystack: string, needle: string): boolean {
  if (needle.length === 0) return false;

  let from = 0;
  for (;;) {
    const index = haystack.indexOf(needle, from);
    if (index === -1) return false;

    const before = index === 0 ? "" : haystack[index - 1];
    const after = haystack[index + needle.length] ?? "";
    if (!isWordCharacter(before) && !isWordCharacter(after)) return true;

    from = index + 1;
  }
}

/**
 * Classify each keyword against the resume text, preserving input order so the
 * sweep reveals them left to right.
 */
export function classifyKeywords(
  resumeText: string,
  keywords: readonly string[],
): ScanKeyword[] {
  const haystack = resumeText.toLowerCase();

  return keywords.map((term) => {
    const needle = term.trim().toLowerCase();
    return {
      term,
      // A blank needle trivially "appears" in any haystack — treat it as
      // missing rather than reporting a match nobody asked for.
      status: containsToken(haystack, needle) ? "matched" : "missing",
    };
  });
}

/** How many keywords the sweep has passed, given normalized progress. */
export function revealedCount(progress: number, total: number): number {
  if (!Number.isFinite(progress) || total <= 0) return 0;
  const clamped = Math.min(1, Math.max(0, progress));
  return Math.round(clamped * total);
}
