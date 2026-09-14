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

function anchorInIssues(anchor: IssueAnchor, issues: BlockingIssue[]): boolean {
  return issues.some(
    (issue) =>
      issue.anchor?.section === anchor.section &&
      issue.anchor.entry_index === anchor.entry_index &&
      issue.anchor.bullet_index === anchor.bullet_index,
  );
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

export function hydratePatchesFromIssues(
  resume: TailoredResumeOutput,
  patches: ResumePatch[],
  issues: BlockingIssue[],
): ResumePatch[] {
  if (!issues.some((issue) => issue.anchor)) return patches;
  return patches.map((patch) => {
    const anchor =
      matchAnchorForPatch(resume, patch, issues) ??
      (patch.anchor && anchorInIssues(patch.anchor, issues) ? patch.anchor : null);
    return hydratePatchFromAnchor(resume, patch, anchor);
  });
}

export function sourceIssueKeysForPatches(
  resume: TailoredResumeOutput,
  patches: ResumePatch[],
  issues: BlockingIssue[],
): (string | undefined)[] {
  return patches.map((patch) => {
    const anchor = patch.anchor ?? matchAnchorForPatch(resume, patch, issues);
    if (!anchor) return undefined;
    const issue = issues.find(
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
