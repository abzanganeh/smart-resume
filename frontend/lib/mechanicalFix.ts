import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";

const KEYWORD_RE =
  /Add ['"\u2018\u2019\u201c\u201d]([^'"\u2018\u2019\u201c\u201d]{1,80})['"\u2018\u2019\u201c\u201d] to the Skills/i;

export function extractMissingKeyword(issue: BlockingIssue): string | null {
  if (issue.category !== "keyword" || issue.fix_effort !== "one_click") {
    return null;
  }
  const match = issue.suggestion.match(KEYWORD_RE);
  return match?.[1]?.trim() ?? null;
}

function flattenSkillTerms(skills: string[]): string[] {
  const terms: string[] = [];
  for (const line of skills) {
    const idx = line.indexOf(":");
    const payload = idx >= 0 ? line.slice(idx + 1) : line;
    for (const part of payload.split(",")) {
      const trimmed = part.trim();
      if (trimmed) terms.push(trimmed);
    }
  }
  return terms;
}

export function applyKeywordToSkills(
  tailored: TailoredResumeOutput,
  keyword: string,
): TailoredResumeOutput | null {
  const term = keyword.trim();
  if (!term) return null;
  const flat = new Set(flattenSkillTerms(tailored.skills ?? []).map((t) => t.toLowerCase()));
  if (flat.has(term.toLowerCase())) return null;

  const skills = [...(tailored.skills ?? [])];
  if (skills.length > 0) {
    const first = skills[0]!;
    if (first.includes(":")) {
      const [prefix, rest] = first.split(":", 2);
      const items = rest.split(",").map((s) => s.trim()).filter(Boolean);
      items.push(term);
      skills[0] = `${prefix}: ${items.join(", ")}`;
    } else {
      skills.push(term);
    }
  } else {
    skills.push(`Skills: ${term}`);
  }

  return { ...tailored, skills };
}

export function tryApplyMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): TailoredResumeOutput | null {
  const keyword = extractMissingKeyword(issue);
  if (!keyword) return null;
  return applyKeywordToSkills(tailored, keyword);
}
