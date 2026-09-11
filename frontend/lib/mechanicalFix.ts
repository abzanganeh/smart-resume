import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";

const ADD_TO_SKILLS_RE =
  /Add ['"\u2018\u2019\u201c\u201d]([^'"\u2018\u2019\u201c\u201d]{1,80})['"\u2018\u2019\u201c\u201d] to the Skills/i;

const REINFORCE_RE =
  /Reinforce ['"\u2018\u2019\u201c\u201d]([^'"\u2018\u2019\u201c\u201d]{1,80})['"\u2018\u2019\u201c\u201d] in your (experience|summary)(?: or (experience|summary))?/i;

export type MechanicalFixChange = { section: string; label: string };

export type MechanicalFixResult = {
  resume: TailoredResumeOutput;
  changes: MechanicalFixChange[];
  unmet: string[];
};

export type MechanicalFixPreview = {
  changes: MechanicalFixChange[];
  unmet: string[];
};

export type EmployerTarget = { company: string; title: string; index: number };

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

function keywordAlreadyInSkills(tailored: TailoredResumeOutput, keyword: string): boolean {
  const flat = new Set(
    flattenSkillTerms(tailored.skills ?? []).map((t) => t.toLowerCase()),
  );
  return flat.has(keyword.trim().toLowerCase());
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

export function resolveEmployerTargets(
  tailored: TailoredResumeOutput,
): EmployerTarget[] {
  return (tailored.experience ?? [])
    .map((exp, index) => ({
      company: (exp.company ?? "").trim(),
      title: (exp.title ?? "").trim(),
      index,
    }))
    .filter((target) => target.company.length > 0 || target.title.length > 0);
}

export function applyKeywordToSkills(
  tailored: TailoredResumeOutput,
  keyword: string,
): TailoredResumeOutput | null {
  const term = keyword.trim();
  if (!term) return null;
  if (keywordAlreadyInSkills(tailored, term)) return null;

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
    return null;
  } else if (!keywordInText(bullets[0]!, term)) {
    bullets[0] = `${bullets[0]!.replace(/\.$/, "")} — ${term}.`;
  } else {
    return null;
  }
  first.bullets = bullets;
  experience[0] = first;
  return { ...tailored, experience };
}

function previewSkillsAdd(
  tailored: TailoredResumeOutput,
  keyword: string,
): MechanicalFixPreview {
  if (keywordAlreadyInSkills(tailored, keyword)) {
    return { changes: [], unmet: ["already in skills"] };
  }
  return {
    changes: [{ section: "Skills", label: `Add ${keyword}` }],
    unmet: [],
  };
}

function previewReinforcement(
  tailored: TailoredResumeOutput,
  keyword: string,
  targets: Array<"experience" | "summary">,
): MechanicalFixPreview {
  const changes: MechanicalFixChange[] = [];
  const unmet: string[] = [];

  for (const target of targets) {
    if (target === "summary") {
      const summary = (tailored.summary ?? "").trim();
      if (keywordInText(summary, keyword)) {
        unmet.push("already in summary");
      } else {
        changes.push({ section: "Summary", label: `Include ${keyword}` });
        break;
      }
    } else {
      const experience = tailored.experience ?? [];
      if (experience.length === 0) {
        unmet.push("no experience entries");
      } else {
        const first = experience[0]!;
        const bullets = first.bullets ?? [];
        if (bullets.length === 0) {
          unmet.push("no experience bullet to reinforce");
          break;
        }
        if (keywordInText(bullets[0]!, keyword)) {
          unmet.push("already in experience");
        } else {
          changes.push({
            section: "Experience",
            label: `Reinforce ${keyword} in ${first.company || first.title || "first role"}`,
          });
          break;
        }
      }
    }
  }

  return { changes, unmet };
}

function applySkillsAdd(
  tailored: TailoredResumeOutput,
  keyword: string,
): MechanicalFixResult | null {
  const preview = previewSkillsAdd(tailored, keyword);
  if (preview.changes.length === 0) {
    return preview.unmet.length > 0 ? { resume: tailored, ...preview } : null;
  }
  const updated = applyKeywordToSkills(tailored, keyword);
  if (!updated) {
    return { resume: tailored, changes: [], unmet: ["already in skills"] };
  }
  return { resume: updated, changes: preview.changes, unmet: preview.unmet };
}

function applyReinforcement(
  tailored: TailoredResumeOutput,
  keyword: string,
  targets: Array<"experience" | "summary">,
): MechanicalFixResult | null {
  const preview = previewReinforcement(tailored, keyword, targets);
  if (preview.changes.length === 0) {
    return preview.unmet.length > 0 ? { resume: tailored, ...preview } : null;
  }

  for (const target of targets) {
    const updated =
      target === "summary"
        ? applyKeywordToSummary(tailored, keyword)
        : applyKeywordToExperience(tailored, keyword);
    if (updated) {
      return {
        resume: updated,
        changes: preview.changes,
        unmet: preview.unmet,
      };
    }
  }

  return { resume: tailored, changes: [], unmet: preview.unmet };
}

export function previewMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): MechanicalFixPreview | null {
  const missing = extractMissingKeyword(issue);
  if (missing) {
    return previewSkillsAdd(tailored, missing);
  }

  const reinforce = extractReinforceKeyword(issue);
  if (reinforce) {
    return previewReinforcement(tailored, reinforce.keyword, reinforce.targets);
  }

  return null;
}

export function tryApplyMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): MechanicalFixResult | null {
  const missing = extractMissingKeyword(issue);
  if (missing) {
    return applySkillsAdd(tailored, missing);
  }

  const reinforce = extractReinforceKeyword(issue);
  if (reinforce) {
    return applyReinforcement(tailored, reinforce.keyword, reinforce.targets);
  }

  return null;
}

export function canApplyMechanicalQuickWin(
  tailored: TailoredResumeOutput,
  issue: BlockingIssue,
): boolean {
  const preview = previewMechanicalQuickWin(tailored, issue);
  return preview !== null && preview.changes.length > 0;
}
