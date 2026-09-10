import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";

const ADD_TO_SKILLS_RE =
  /Add ['"\u2018\u2019\u201c\u201d]([^'"\u2018\u2019\u201c\u201d]{1,80})['"\u2018\u2019\u201c\u201d] to the Skills/i;

const REINFORCE_RE =
  /Reinforce ['"\u2018\u2019\u201c\u201d]([^'"\u2018\u2019\u201c\u201d]{1,80})['"\u2018\u2019\u201c\u201d] in your (experience|summary)(?: or (experience|summary))?/i;

export function extractMissingKeyword(issue: BlockingIssue): string | null {
  if (issue.category !== "keyword" || issue.fix_effort !== "one_click") {
    return null;
  }
  const match = issue.suggestion.match(ADD_TO_SKILLS_RE);
  return match?.[1]?.trim() ?? null;
}

export function extractReinforceKeyword(
  issue: BlockingIssue,
): { keyword: string; targets: Array<"experience" | "summary"> } | null {
  if (issue.category !== "keyword" || issue.fix_effort !== "one_click") {
    return null;
  }
  const match = issue.suggestion.match(REINFORCE_RE);
  if (!match?.[1]) return null;
  const targets = [match[2], match[3]].filter(
    (value): value is "experience" | "summary" =>
      value === "experience" || value === "summary",
  );
  return {
    keyword: match[1].trim(),
    targets: targets.length > 0 ? targets : ["experience"],
  };
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

function keywordInText(text: string, keyword: string): boolean {
  return text.toLowerCase().includes(keyword.toLowerCase());
}

function findSkillCategoryLine(skills: string[], keyword: string): number {
  const kw = keyword.toLowerCase();
  for (let i = 0; i < skills.length; i++) {
    const line = skills[i];
    const idx = line.indexOf(":");
    if (idx < 0) continue;
    const header = line.slice(0, idx).trim().toLowerCase();
    if (header.includes(kw) || kw.includes(header)) return i;
  }
  return -1;
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
  const categoryIdx = findSkillCategoryLine(skills, term);
  if (categoryIdx >= 0) {
    const line = skills[categoryIdx]!;
    const [prefix, rest] = line.split(":", 2);
    const items = rest.split(",").map((s) => s.trim()).filter(Boolean);
    items.push(term);
    skills[categoryIdx] = `${prefix}: ${items.join(", ")}`;
  } else if (skills.length > 0) {
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

export function applyKeywordToSummary(
  tailored: TailoredResumeOutput,
  keyword: string,
): TailoredResumeOutput | null {
  const term = keyword.trim();
  if (!term) return null;
  const summary = (tailored.summary ?? "").trim();
  if (keywordInText(summary, term)) return null;
  const addition = summary
    ? `${summary.replace(/\.$/, "")} — includes ${term}.`
    : `Experienced with ${term}.`;
  return { ...tailored, summary: addition };
}

export function applyKeywordToExperience(
  tailored: TailoredResumeOutput,
  keyword: string,
): TailoredResumeOutput | null {
  const term = keyword.trim();
  if (!term) return null;
  const experience = [...(tailored.experience ?? [])];
  if (experience.length === 0) return null;

  const first = { ...experience[0]! };
  const bullets = [...(first.bullets ?? [])];
  if (bullets.length === 0) {
    bullets.push(`Delivered ${term} in production customer environments.`);
  } else if (!keywordInText(bullets[0]!, term)) {
    bullets[0] = `${bullets[0]!.replace(/\.$/, "")} — ${term}.`;
  } else {
    return null;
  }
  first.bullets = bullets;
  experience[0] = first;
  return { ...tailored, experience };
}

function applyKeywordReinforcement(
  tailored: TailoredResumeOutput,
  keyword: string,
  targets: Array<"experience" | "summary">,
): TailoredResumeOutput | null {
  for (const target of targets) {
    const updated =
      target === "summary"
        ? applyKeywordToSummary(tailored, keyword)
        : applyKeywordToExperience(tailored, keyword);
    if (updated) return updated;
  }
  return null;
}

export function tryApplyMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): TailoredResumeOutput | null {
  const missing = extractMissingKeyword(issue);
  if (missing) {
    let updated = applyKeywordToSkills(tailored, missing) ?? tailored;
    const reinforced = applyKeywordReinforcement(updated, missing, [
      "summary",
      "experience",
    ]);
    return reinforced ?? (updated !== tailored ? updated : null);
  }

  const reinforce = extractReinforceKeyword(issue);
  if (reinforce) {
    return applyKeywordReinforcement(tailored, reinforce.keyword, reinforce.targets);
  }

  return null;
}

export function canApplyMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): boolean {
  return tryApplyMechanicalQuickWin(tailored, issue) !== null;
}
