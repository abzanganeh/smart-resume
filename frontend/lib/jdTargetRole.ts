const LOGO_LINE = /\blogo\b/i;
const BOILERPLATE_PREFIXES = ["apply for this job", "jobs powered by", "home page", "salary:"];

/** Infer a job title from JD plain text, skipping logo alt-text and nav chrome. */
export function inferJdTargetRole(jdText: string, explicitTitle?: string | null): string {
  const fromApi = explicitTitle?.trim();
  if (fromApi) return fromApi;

  const lines = jdText
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);

  for (const line of lines) {
    if (line.length > 120) continue;
    const lower = line.toLowerCase();
    if (LOGO_LINE.test(line)) continue;
    if (BOILERPLATE_PREFIXES.some((prefix) => lower.startsWith(prefix))) continue;
    if (line.includes("|") && line.length > 80) continue;
    return line;
  }

  return "";
}
