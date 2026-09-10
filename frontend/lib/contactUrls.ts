const LABEL_ONLY: Record<"linkedin" | "github", RegExp> = {
  linkedin: /^(linked\s*in|linkedin\.?)$/i,
  github: /^(git\s*hub|github\.?)$/i,
};

/** Drop label-only values (e.g. "LinkedIn") and normalize bare profile URLs. */
export function sanitizeContactUrl(
  kind: "linkedin" | "github",
  value: string | null | undefined,
): string {
  const trimmed = (value ?? "").trim();
  if (!trimmed) return "";

  if (LABEL_ONLY[kind].test(trimmed)) return "";

  if (/^https?:\/\//i.test(trimmed)) return trimmed;

  if (kind === "linkedin" && /linkedin\.com/i.test(trimmed)) {
    return trimmed.toLowerCase().startsWith("http") ? trimmed : `https://${trimmed}`;
  }

  if (kind === "github" && /github\.com/i.test(trimmed)) {
    return trimmed.toLowerCase().startsWith("http") ? trimmed : `https://${trimmed}`;
  }

  if (kind === "github" && /^[a-z0-9]([a-z0-9-]{0,37})$/i.test(trimmed)) {
    return `https://github.com/${trimmed}`;
  }

  if (!/[./@]/.test(trimmed)) return "";

  return trimmed;
}
