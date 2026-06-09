import {
  inferEducationInstitution,
  matchEducationInstitution,
  matchExperienceCompany,
  matchProjectName,
} from "@/lib/applyResumePatch";
import type { TailoredEducation } from "@/lib/api";
import type { ResumeSuggestion } from "@/lib/suggestions";

export type HighlightTone = "none" | "pending" | "accepted" | "rejected";

export const HIGHLIGHT: Record<HighlightTone, string> = {
  none: "",
  pending: "bg-amber-500/12 border border-amber-500/40",
  accepted: "bg-emerald-500/12 border border-emerald-500/40",
  rejected: "bg-red-500/12 border border-red-500/40 opacity-75",
};

export function normalizeText(value: string): string {
  return value.trim().replace(/\s+/g, " ");
}

export function textsMatch(a: string, b: string): boolean {
  const left = normalizeText(a);
  const right = normalizeText(b);
  if (!left || !right) return false;
  return left === right || left.includes(right) || right.includes(left);
}

export function toneForSuggestion(sug: ResumeSuggestion): HighlightTone {
  if (sug.status === "pending") return "pending";
  if (sug.status === "accepted") return "accepted";
  return "rejected";
}

// ── Summary ───────────────────────────────────────────────────────────────────

export function summarySuggestions(suggestions: ResumeSuggestion[]) {
  return suggestions.filter((s) => s.patch.section === "summary" && s.patch.new_summary?.trim());
}

export function activeSummarySuggestion(suggestions: ResumeSuggestion[]) {
  return summarySuggestions(suggestions).find((s) => s.status !== "rejected");
}

// ── Skills ────────────────────────────────────────────────────────────────────

export function skillsSuggestions(suggestions: ResumeSuggestion[]) {
  return suggestions.filter(
    (s) =>
      s.patch.section === "skills" &&
      ((s.patch.add_skills?.length ?? 0) > 0 || (s.patch.remove_skills?.length ?? 0) > 0),
  );
}

export function pendingSkillAdds(suggestions: ResumeSuggestion[]): string[] {
  return skillsSuggestions(suggestions)
    .filter((s) => s.status === "pending")
    .flatMap((s) => s.patch.add_skills ?? []);
}

export function pendingSkillRemoves(suggestions: ResumeSuggestion[]) {
  const names = new Set<string>();
  for (const s of skillsSuggestions(suggestions).filter((x) => x.status === "pending")) {
    for (const name of s.patch.remove_skills ?? []) names.add(name);
  }
  return names;
}

export function acceptedSkillAdds(suggestions: ResumeSuggestion[]): Set<string> {
  const names = new Set<string>();
  for (const s of skillsSuggestions(suggestions).filter((x) => x.status === "accepted")) {
    for (const name of s.patch.add_skills ?? []) names.add(normalizeText(name).toLowerCase());
  }
  return names;
}

export function skillChipTone(
  skill: string,
  suggestions: ResumeSuggestion[],
  pendingRemoves: Set<string>,
  acceptedAdds: Set<string>,
): HighlightTone {
  const key = normalizeText(skill).toLowerCase();
  if (pendingRemoves.has(skill) || [...pendingRemoves].some((r) => textsMatch(r, skill))) {
    return "pending";
  }
  if (acceptedAdds.has(key)) return "accepted";
  return "none";
}

// ── Experience ────────────────────────────────────────────────────────────────

export function experienceSuggestions(suggestions: ResumeSuggestion[], company: string) {
  return suggestions.filter(
    (s) =>
      s.patch.section === "experience" &&
      matchExperienceCompany(company, s.patch.company ?? ""),
  );
}

export function bulletEditSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
  bulletText: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) =>
      s.patch.bullet_old &&
      s.patch.bullet_new &&
      textsMatch(s.patch.bullet_old, bulletText),
  );
}

export function acceptedBulletSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
  bulletText: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) =>
      s.status === "accepted" &&
      s.patch.bullet_new &&
      textsMatch(s.patch.bullet_new, bulletText),
  );
}

export function titleSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) => s.patch.new_title?.trim() && !s.patch.bullet_old,
  );
}

export function datesSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) => !!s.patch.new_dates?.trim(),
  );
}

// ── Education ─────────────────────────────────────────────────────────────────

function suggestionTargetsInstitution(
  patch: import("@/lib/api").ResumePatch,
  institution: string,
  allEducation: TailoredEducation[],
): boolean {
  if (patch.section !== "education") return false;
  const inferred = inferEducationInstitution(allEducation, patch);
  if (!inferred) return false;
  return matchEducationInstitution(institution, inferred.institution);
}

export function educationSuggestions(
  suggestions: ResumeSuggestion[],
  institution: string,
  allEducation: TailoredEducation[],
) {
  return suggestions.filter((s) =>
    suggestionTargetsInstitution(s.patch, institution, allEducation),
  );
}

export function institutionRenameSuggestion(
  suggestions: ResumeSuggestion[],
  institution: string,
  allEducation: TailoredEducation[],
): ResumeSuggestion | undefined {
  return educationSuggestions(suggestions, institution, allEducation).find(
    (s) => !!s.patch.new_institution?.trim(),
  );
}

export function educationBulletAddSuggestions(
  suggestions: ResumeSuggestion[],
  institution: string,
  allEducation: TailoredEducation[],
): ResumeSuggestion[] {
  return educationSuggestions(suggestions, institution, allEducation).filter(
    (s) => (s.patch.add_education_bullets?.length ?? 0) > 0,
  );
}

export function hasPendingEducationSuggestions(
  suggestions: ResumeSuggestion[],
  institution: string,
  allEducation: TailoredEducation[],
): boolean {
  return educationSuggestions(suggestions, institution, allEducation).some(
    (s) => s.status === "pending",
  );
}

// ── Projects ──────────────────────────────────────────────────────────────────

export function projectEditSuggestions(suggestions: ResumeSuggestion[], projectName: string) {
  return suggestions.filter(
    (s) =>
      s.patch.section === "projects" &&
      !s.patch.new_project &&
      !(s.patch.remove_projects?.length) &&
      matchProjectName(projectName, s.patch.project_name ?? ""),
  );
}

export function projectBulletEditSuggestion(
  suggestions: ResumeSuggestion[],
  projectName: string,
  bulletText: string,
): ResumeSuggestion | undefined {
  return projectEditSuggestions(suggestions, projectName).find(
    (s) =>
      s.patch.project_bullet_old &&
      s.patch.project_bullet_new &&
      textsMatch(s.patch.project_bullet_old, bulletText),
  );
}

export function acceptedProjectBulletSuggestion(
  suggestions: ResumeSuggestion[],
  projectName: string,
  bulletText: string,
): ResumeSuggestion | undefined {
  return projectEditSuggestions(suggestions, projectName).find(
    (s) =>
      s.status === "accepted" &&
      s.patch.project_bullet_new &&
      textsMatch(s.patch.project_bullet_new, bulletText),
  );
}

export function projectReplaceAllSuggestion(
  suggestions: ResumeSuggestion[],
  projectName: string,
): ResumeSuggestion | undefined {
  return projectEditSuggestions(suggestions, projectName).find(
    (s) => (s.patch.project_bullets_replace_all?.length ?? 0) > 0,
  );
}

export function newProjectSuggestions(suggestions: ResumeSuggestion[]) {
  return suggestions.filter(
    (s) => s.patch.section === "projects" && !!s.patch.new_project?.name?.trim(),
  );
}

export function projectRemovalSuggestions(suggestions: ResumeSuggestion[]) {
  return suggestions.filter((s) => (s.patch.remove_projects?.length ?? 0) > 0);
}

export function projectRemovalPending(
  suggestions: ResumeSuggestion[],
  projectName: string,
): ResumeSuggestion | undefined {
  return projectRemovalSuggestions(suggestions)
    .filter((s) => s.status === "pending")
    .find((s) =>
      (s.patch.remove_projects ?? []).some((name) => matchProjectName(projectName, name)),
    );
}

export function placedSuggestionIds(
  suggestions: ResumeSuggestion[],
  resume: import("@/lib/api").TailoredResumeOutput,
): Set<string> {
  const placed = new Set<string>();
  for (const s of summarySuggestions(suggestions)) placed.add(s.id);
  for (const s of skillsSuggestions(suggestions)) placed.add(s.id);
  for (const exp of resume.experience) {
    for (const s of experienceSuggestions(suggestions, exp.company)) placed.add(s.id);
  }
  for (const proj of resume.projects) {
    const name = String((proj as Record<string, unknown>).name ?? "");
    for (const s of projectEditSuggestions(suggestions, name)) placed.add(s.id);
    const removal = projectRemovalPending(suggestions, name);
    if (removal) placed.add(removal.id);
  }
  for (const edu of resume.education) {
    for (const s of educationSuggestions(suggestions, edu.institution, resume.education)) {
      placed.add(s.id);
    }
  }
  for (const s of suggestions) {
    if (s.patch.section === "education" && inferEducationInstitution(resume.education, s.patch)) {
      placed.add(s.id);
    }
  }
  for (const s of newProjectSuggestions(suggestions)) placed.add(s.id);
  for (const s of projectRemovalSuggestions(suggestions)) placed.add(s.id);
  return placed;
}

export function pendingSuggestionCount(suggestions: ResumeSuggestion[]): number {
  return suggestions.filter((s) => s.status === "pending").length;
}

export function orphanedSuggestions(
  suggestions: ResumeSuggestion[],
  resume: import("@/lib/api").TailoredResumeOutput,
) {
  const placed = placedSuggestionIds(suggestions, resume);
  return suggestions.filter((s) => !placed.has(s.id));
}
