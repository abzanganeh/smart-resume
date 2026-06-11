import {
  inferEducationInstitution,
  matchEducationInstitution,
  matchExperienceCompany,
  matchProjectName,
} from "@/lib/applyResumePatch";
import type { ResumePatch, TailoredEducation, TailoredResumeOutput } from "@/lib/api";
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

// ── Contact ───────────────────────────────────────────────────────────────────

export function contactNameSuggestion(
  suggestions: ResumeSuggestion[],
): ResumeSuggestion | undefined {
  return suggestions.find(
    (s) => s.patch.section === "contact" && !!s.patch.new_name?.trim() && s.status !== "rejected",
  );
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

export function dismissExperienceBulletSuggestions(
  suggestions: ResumeSuggestion[],
  onDismiss: ((id: string) => void) | undefined,
  company: string,
  bulletTexts: string[],
) {
  if (!onDismiss) return;
  const texts = bulletTexts.map((t) => normalizeText(t)).filter(Boolean);
  if (!texts.length) return;
  for (const s of suggestions) {
    if (s.patch.section !== "experience") continue;
    if (!matchExperienceCompany(company, s.patch.company ?? "")) continue;
    const old = s.patch.bullet_old ? normalizeText(s.patch.bullet_old) : "";
    const next = s.patch.bullet_new ? normalizeText(s.patch.bullet_new) : "";
    const tied = texts.some(
      (t) =>
        (old && textsMatch(old, t)) ||
        (next && textsMatch(next, t)),
    );
    if (tied) onDismiss(s.id);
  }
}

export function dismissProjectBulletSuggestions(
  suggestions: ResumeSuggestion[],
  onDismiss: ((id: string) => void) | undefined,
  projectName: string,
  bulletTexts: string[],
) {
  if (!onDismiss) return;
  const texts = bulletTexts.map((t) => normalizeText(t)).filter(Boolean);
  if (!texts.length) return;
  for (const s of suggestions) {
    if (s.patch.section !== "projects") continue;
    if (!matchProjectName(projectName, s.patch.project_name ?? "")) continue;
    const old = s.patch.project_bullet_old ? normalizeText(s.patch.project_bullet_old) : "";
    const next = s.patch.project_bullet_new ? normalizeText(s.patch.project_bullet_new) : "";
    const tied = texts.some(
      (t) =>
        (old && textsMatch(old, t)) ||
        (next && textsMatch(next, t)),
    );
    if (tied) onDismiss(s.id);
  }
}

export function titleSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) => s.patch.new_title?.trim() && !s.patch.bullet_old && !s.patch.delete_experience,
  );
}

export function experienceDeleteSuggestion(
  suggestions: ResumeSuggestion[],
  company: string,
): ResumeSuggestion | undefined {
  return experienceSuggestions(suggestions, company).find(
    (s) => s.patch.delete_experience && s.status === "pending",
  );
}

export function certificationRemovalSuggestions(suggestions: ResumeSuggestion[]) {
  return suggestions.filter(
    (s) =>
      s.patch.section === "certifications" &&
      (s.patch.remove_certifications?.length ?? 0) > 0,
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

function projectDisplayName(project: Record<string, unknown>): string {
  return String(project.name ?? "").trim();
}

/** True when this patch targets something that exists in the current resume. */
export function isPatchPlaceable(
  patch: ResumePatch,
  resume: TailoredResumeOutput,
): boolean {
  if (patch.section === "contact" && patch.new_name?.trim()) {
    return true;
  }

  if (patch.section === "summary" && patch.new_summary?.trim()) {
    return true;
  }

  if (patch.section === "skills") {
    if (patch.add_skills?.length) return true;
    if (patch.remove_skills?.length) {
      return patch.remove_skills.some((skill) =>
        resume.skills.some((s) => textsMatch(s, skill)),
      );
    }
    return false;
  }

  if (patch.section === "experience" && patch.company?.trim()) {
    const idx = resume.experience.findIndex((exp) =>
      matchExperienceCompany(exp.company, patch.company!),
    );
    if (idx < 0) return false;
    const exp = resume.experience[idx]!;
    if (patch.delete_experience) return true;
    if (patch.new_title?.trim() || patch.new_dates?.trim()) return true;
    if (patch.bullet_old?.trim()) {
      return exp.bullets.some((b) => b === patch.bullet_old || textsMatch(b, patch.bullet_old!));
    }
    return false;
  }

  if (patch.section === "education" && patch.institution?.trim()) {
    return resume.education.some((edu) =>
      matchEducationInstitution(edu.institution, patch.institution!),
    );
  }

  if (patch.section === "certifications") {
    if (patch.add_certifications?.length) return true;
    if (patch.remove_certifications?.length) {
      return patch.remove_certifications.some((cert) => resume.certifications.includes(cert));
    }
    return false;
  }

  if (patch.section === "projects") {
    if (patch.new_project?.name?.trim()) {
      const name = patch.new_project.name.trim();
      return !resume.projects.some((proj) =>
        matchProjectName(projectDisplayName(proj as Record<string, unknown>), name),
      );
    }
    if (patch.remove_projects?.length) {
      return patch.remove_projects.some((target) =>
        resume.projects.some((proj) =>
          matchProjectName(projectDisplayName(proj as Record<string, unknown>), target),
        ),
      );
    }
    if (patch.project_name?.trim()) {
      return resume.projects.some((proj) =>
        matchProjectName(
          projectDisplayName(proj as Record<string, unknown>),
          patch.project_name!,
        ),
      );
    }
    return false;
  }

  return false;
}

export function countPlaceablePatches(
  patches: ResumePatch[],
  resume: TailoredResumeOutput,
): { placeable: number; unplaceable: number } {
  let placeable = 0;
  for (const patch of patches) {
    if (isPatchPlaceable(patch, resume)) placeable += 1;
  }
  return { placeable, unplaceable: patches.length - placeable };
}

export function placedSuggestionIds(
  suggestions: ResumeSuggestion[],
  resume: TailoredResumeOutput,
): Set<string> {
  const placed = new Set<string>();
  for (const s of suggestions) {
    if (isPatchPlaceable(s.patch, resume)) {
      placed.add(s.id);
    }
  }
  return placed;
}

export function pendingSuggestionCount(suggestions: ResumeSuggestion[]): number {
  return suggestions.filter((s) => s.status === "pending").length;
}

export function orphanedSuggestions(
  suggestions: ResumeSuggestion[],
  resume: TailoredResumeOutput,
) {
  const placed = placedSuggestionIds(suggestions, resume);
  return suggestions.filter((s) => s.status === "pending" && !placed.has(s.id));
}
