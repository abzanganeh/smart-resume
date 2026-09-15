import { matchExperienceCompany, matchProjectName } from "@/lib/applyResumePatch";
import type { BlockingIssue, IssueAnchor, ResumePatch, TailoredResumeOutput } from "@/lib/api";

export function resolveBulletAtAnchor(
  resume: TailoredResumeOutput,
  anchor: IssueAnchor,
): {
  section: IssueAnchor["section"];
  company?: string;
  project_name?: string;
  institution?: string;
  bullet_old?: string;
  project_bullet_old?: string;
  education_bullet_old?: string;
} | null {
  const bulletIndex = anchor.bullet_index;
  if (bulletIndex == null) return null;

  if (anchor.section === "experience") {
    const entry = resume.experience[anchor.entry_index];
    const bullet = entry?.bullets[bulletIndex];
    const company = entry?.company?.trim();
    if (!entry || !company || !bullet) return null;
    return { section: "experience", company, bullet_old: bullet };
  }

  if (anchor.section === "projects") {
    const entry = resume.projects[anchor.entry_index] as { name?: string; bullets?: string[] } | undefined;
    const bullet = entry?.bullets?.[bulletIndex];
    const name = entry?.name?.trim();
    if (!entry || !name || !bullet) return null;
    return { section: "projects", project_name: name, project_bullet_old: bullet };
  }

  const entry = resume.education[anchor.entry_index];
  const bullet = entry?.bullets?.[bulletIndex];
  const institution = entry?.institution?.trim();
  if (!entry || !institution || !bullet) return null;
  return { section: "education", institution, education_bullet_old: bullet };
}

export function hydratePatchFromAnchor(
  resume: TailoredResumeOutput,
  patch: ResumePatch,
  anchor?: IssueAnchor | null,
): ResumePatch {
  if (!anchor) return patch;
  const resolved = resolveBulletAtAnchor(resume, anchor);
  if (!resolved) {
    return { ...patch, anchor };
  }

  if (resolved.section === "experience") {
    return {
      ...patch,
      anchor,
      section: "experience",
      company: resolved.company,
      bullet_old: resolved.bullet_old,
    };
  }
  if (resolved.section === "projects") {
    return {
      ...patch,
      anchor,
      section: "projects",
      project_name: resolved.project_name,
      project_bullet_old: resolved.project_bullet_old,
    };
  }
  return {
    ...patch,
    anchor,
    section: "education",
    institution: resolved.institution,
    education_bullet_old: resolved.education_bullet_old,
  };
}

function normalizeBulletText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

function bulletHintMatches(candidate: string, hint: string): boolean {
  const bullet = normalizeBulletText(candidate);
  const needle = normalizeBulletText(hint.replace(/…$/, ""));
  if (!bullet || !needle) return false;
  if (bullet === needle) return true;
  if (bullet.startsWith(needle) || needle.startsWith(bullet)) return true;
  const prefixLen = 16;
  if (needle.length >= prefixLen && bullet.includes(needle.slice(0, prefixLen))) return true;
  return false;
}

function bulletHintFromIssue(issue: BlockingIssue): string | null {
  const text = issue.suggestion.trim();
  if (!text) return null;
  const hint = text.split(":").pop()?.trim().replace(/…$/, "").trim() ?? "";
  return hint.length >= 8 ? hint : null;
}

export function inferAnchorFromIssue(
  resume: TailoredResumeOutput,
  issue: BlockingIssue,
): IssueAnchor | null {
  if (issue.anchor) return issue.anchor;
  const hint = bulletHintFromIssue(issue);
  if (!hint) return null;

  const matches: IssueAnchor[] = [];
  resume.experience.forEach((entry, entryIndex) => {
    entry.bullets.forEach((bullet, bulletIndex) => {
      if (bulletHintMatches(bullet, hint)) {
        matches.push({ section: "experience", entry_index: entryIndex, bullet_index: bulletIndex });
      }
    });
  });
  (resume.projects ?? []).forEach((entry, entryIndex) => {
    const bullets = Array.isArray((entry as { bullets?: string[] }).bullets)
      ? (entry as { bullets: string[] }).bullets
      : [];
    bullets.forEach((bullet, bulletIndex) => {
      if (bulletHintMatches(bullet, hint)) {
        matches.push({ section: "projects", entry_index: entryIndex, bullet_index: bulletIndex });
      }
    });
  });
  resume.education.forEach((entry, entryIndex) => {
    (entry.bullets ?? []).forEach((bullet, bulletIndex) => {
      if (bulletHintMatches(bullet, hint)) {
        matches.push({ section: "education", entry_index: entryIndex, bullet_index: bulletIndex });
      }
    });
  });
  return matches.length === 1 ? matches[0]! : null;
}

export function enrichIssuesWithInferredAnchors(
  resume: TailoredResumeOutput,
  issues: BlockingIssue[],
): BlockingIssue[] {
  return issues.map((issue) => {
    const anchor = inferAnchorFromIssue(resume, issue);
    if (!anchor || issue.anchor) return issue;
    return { ...issue, anchor };
  });
}

function anchorInIssues(anchor: IssueAnchor, issues: BlockingIssue[]): boolean {
  return issues.some(
    (issue) =>
      issue.anchor?.section === anchor.section &&
      issue.anchor.entry_index === anchor.entry_index &&
      issue.anchor.bullet_index === anchor.bullet_index,
  );
}

function patchConflictsWithAnchor(
  resume: TailoredResumeOutput,
  patch: ResumePatch,
  anchor: IssueAnchor,
): boolean {
  const resolved = resolveBulletAtAnchor(resume, anchor);
  if (!resolved) return true;
  if (resolved.section === "experience" && patch.section === "experience") {
    const company = patch.company?.trim();
    return Boolean(company && !matchExperienceCompany(company, resolved.company ?? ""));
  }
  if (resolved.section === "projects" && patch.section === "projects") {
    const projectName = patch.project_name?.trim();
    return Boolean(
      projectName && !matchProjectName(projectName, resolved.project_name ?? ""),
    );
  }
  if (resolved.section === "education" && patch.section === "education") {
    const institution = patch.institution?.trim();
    return Boolean(
      institution &&
        institution.toLowerCase() !== (resolved.institution ?? "").toLowerCase(),
    );
  }
  return false;
}

function patchContentMatchesAnchor(
  resume: TailoredResumeOutput,
  patch: ResumePatch,
  anchor: IssueAnchor,
): boolean {
  const resolved = resolveBulletAtAnchor(resume, anchor);
  if (!resolved) return false;
  if (resolved.section === "experience" && patch.section === "experience") {
    const company = patch.company?.trim();
    const bulletOld = patch.bullet_old?.trim();
    if (company && !matchExperienceCompany(company, resolved.company ?? "")) return false;
    if (bulletOld && resolved.bullet_old && !bulletHintMatches(resolved.bullet_old, bulletOld)) {
      return false;
    }
    return true;
  }
  if (resolved.section === "projects" && patch.section === "projects") {
    const projectName = patch.project_name?.trim();
    const bulletOld = patch.project_bullet_old?.trim();
    if (projectName && !matchProjectName(projectName, resolved.project_name ?? "")) return false;
    if (
      bulletOld &&
      resolved.project_bullet_old &&
      !bulletHintMatches(resolved.project_bullet_old, bulletOld)
    ) {
      return false;
    }
    return true;
  }
  if (resolved.section === "education" && patch.section === "education") {
    const institution = patch.institution?.trim();
    const bulletOld = patch.education_bullet_old?.trim();
    if (institution && institution.toLowerCase() !== (resolved.institution ?? "").toLowerCase()) {
      return false;
    }
    if (
      bulletOld &&
      resolved.education_bullet_old &&
      !bulletHintMatches(resolved.education_bullet_old, bulletOld)
    ) {
      return false;
    }
    return true;
  }
  return false;
}

export function matchAnchorForPatch(
  resume: TailoredResumeOutput,
  patch: ResumePatch,
  issues: BlockingIssue[],
): IssueAnchor | null {
  const matches: IssueAnchor[] = [];
  for (const issue of issues) {
    if (!issue.anchor) continue;
    const resolved = resolveBulletAtAnchor(resume, issue.anchor);
    if (!resolved) continue;
    if (resolved.section === "experience" && patch.section === "experience") {
      const company = patch.company?.trim();
      if (company && matchExperienceCompany(company, resolved.company ?? "")) {
        matches.push(issue.anchor);
        continue;
      }
      if (patch.bullet_new && !company) {
        matches.push(issue.anchor);
      }
    } else if (resolved.section === "projects" && patch.section === "projects") {
      const projectName = patch.project_name?.trim();
      if (projectName && matchProjectName(projectName, resolved.project_name ?? "")) {
        matches.push(issue.anchor);
        continue;
      }
      if (patch.project_bullet_new && !projectName) {
        matches.push(issue.anchor);
      }
    }
  }
  return matches.length === 1 ? matches[0] : null;
}

function anchorForPatchIndex(
  resume: TailoredResumeOutput,
  patch: ResumePatch,
  issues: BlockingIssue[],
  patchIndex: number,
): IssueAnchor | null {
  const matched = matchAnchorForPatch(resume, patch, issues);
  if (matched) return matched;
  const positional = issues[patchIndex]?.anchor;
  if (positional) {
    if (issues.length === 1 || !patchConflictsWithAnchor(resume, patch, positional)) {
      return positional;
    }
  }
  return patch.anchor && anchorInIssues(patch.anchor, issues) ? patch.anchor : null;
}

export function hydratePatchesFromIssues(
  resume: TailoredResumeOutput,
  patches: ResumePatch[],
  issues: BlockingIssue[],
): ResumePatch[] {
  const enriched = enrichIssuesWithInferredAnchors(resume, issues);
  if (!enriched.some((issue) => issue.anchor)) return patches;
  return patches.map((patch, index) =>
    hydratePatchFromAnchor(
      resume,
      patch,
      anchorForPatchIndex(resume, patch, enriched, index),
    ),
  );
}

export function sourceIssueKeysForPatches(
  resume: TailoredResumeOutput,
  patches: ResumePatch[],
  issues: BlockingIssue[],
): (string | undefined)[] {
  const enriched = enrichIssuesWithInferredAnchors(resume, issues);
  return patches.map((patch) => {
    const anchor = patch.anchor ?? matchAnchorForPatch(resume, patch, enriched);
    if (!anchor) return undefined;
    const issue = enriched.find(
      (candidate) =>
        candidate.anchor?.section === anchor.section &&
        candidate.anchor.entry_index === anchor.entry_index &&
        candidate.anchor.bullet_index === anchor.bullet_index,
    );
    return issue ? issueAnchorKey(issue) : undefined;
  });
}

export function buildBatchChatMessage(
  issues: BlockingIssue[],
  tailored: TailoredResumeOutput | null,
): string {
  const lines = issues.map((issue, index) => {
    const resolved =
      issue.anchor && tailored ? resolveBulletAtAnchor(tailored, issue.anchor) : null;
    const exactBullet =
      resolved?.bullet_old ??
      resolved?.project_bullet_old ??
      resolved?.education_bullet_old;
    const location =
      resolved?.company != null
        ? `company="${resolved.company}"`
        : resolved?.project_name != null
          ? `project="${resolved.project_name}"`
          : resolved?.institution != null
            ? `institution="${resolved.institution}"`
            : null;
    const bulletLine = exactBullet
      ? `\n   EXACT current bullet: "${exactBullet}"`
      : "";
    const locationLine = location ? `\n   Location: ${location}` : "";
    return `${index + 1}. [${issue.category}] ${issue.description}\n   Suggestion: ${issue.suggestion}${locationLine}${bulletLine}`;
  });
  return `Address these ${issues.length} issues in my resume in a single round of edits:\n\n${lines.join("\n\n")}\n\nReturn one patch per issue above, in order. Use the EXACT current bullet text for bullet_old when provided.`;
}

export function issueAnchorKey(issue: BlockingIssue): string {
  if (!issue.anchor) {
    return `${issue.category}|${issue.description}|${issue.suggestion}`;
  }
  const { section, entry_index, bullet_index } = issue.anchor;
  return `anchor:${section}:${entry_index}:${bullet_index ?? "x"}`;
}
