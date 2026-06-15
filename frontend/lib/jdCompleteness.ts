/** Detect when auto-captured JD text should be reviewed before analysis. */

const UNCERTAIN_JD_HOST_PATTERNS = [
  "jobright.ai",
  "linkedin.com",
  "indeed.com",
  "glassdoor.com",
  "ziprecruiter.com",
  "monster.com",
  "builtin.com",
  "wellfound.com",
  "dice.com",
  "simplyhired.com",
  "careerbuilder.com",
  "hiring.cafe",
  "otta.com",
  "talent.com",
  "snagajob.com",
];

export function shouldReviewExtensionJd(
  source: string | null | undefined,
  url: string | null | undefined,
  explicitReviewFlag?: boolean,
): boolean {
  if (explicitReviewFlag) return true;
  if (source !== "extension") return false;
  if (!url?.trim()) return true;
  try {
    const host = new URL(url).hostname.toLowerCase();
    return UNCERTAIN_JD_HOST_PATTERNS.some((pattern) => host.includes(pattern));
  } catch {
    return true;
  }
}

export function uncertainJdHostLabel(url: string | null | undefined): string | null {
  if (!url?.trim()) return null;
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return null;
  }
}
