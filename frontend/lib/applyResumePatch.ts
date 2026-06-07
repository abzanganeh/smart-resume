import type { ResumePatch, TailoredExperience, TailoredResumeOutput } from "@/lib/api";

export interface ApplyResumePatchResult {
  updated: TailoredResumeOutput;
  applied: boolean;
  failureReason?: string;
}

/** Leading token before em dash / hyphen (e.g. "ENTROS" from "ENTROS — Mobile…"). */
function projectNameHead(name: string): string {
  return name.split(/[—–\-|]/)[0]?.trim().toLowerCase() ?? name.trim().toLowerCase();
}

/** Match project by full name or leading token (handles "Entros" vs "ENTROS — …"). */
export function matchProjectName(actualName: string, patchName: string): boolean {
  const a = actualName.trim().toLowerCase();
  const b = patchName.trim().toLowerCase();
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.includes(b) || b.includes(a)) return true;
  const aHead = projectNameHead(actualName);
  const bHead = projectNameHead(patchName);
  return aHead === bHead || aHead.includes(bHead) || bHead.includes(aHead);
}

function projectDisplayName(project: Record<string, unknown>): string {
  return String(project.name ?? "").trim();
}

/** Case-insensitive company match (handles minor LLM / formatting drift). */
export function matchExperienceCompany(
  entryCompany: string,
  patchCompany: string,
): boolean {
  const a = entryCompany.trim().toLowerCase();
  const b = patchCompany.trim().toLowerCase();
  if (!a || !b) return false;
  return a === b || a.includes(b) || b.includes(a);
}

function findExperienceIndex(
  experience: TailoredExperience[],
  patchCompany: string,
): number {
  return experience.findIndex((exp) => matchExperienceCompany(exp.company, patchCompany));
}

/** LLMs often put title edits in bullet_old/bullet_new — remap before apply. */
export function coerceExperiencePatch(
  exp: TailoredExperience,
  patch: ResumePatch,
): ResumePatch {
  if (patch.section !== "experience") return patch;
  if (patch.new_title?.trim() || patch.new_dates?.trim()) return patch;
  if (!patch.bullet_old?.trim() || !patch.bullet_new?.trim()) return patch;

  const old = patch.bullet_old.trim();
  const neu = patch.bullet_new.trim();

  // Title-only change disguised as a bullet patch
  if (old === exp.title.trim() && !exp.bullets.includes(patch.bullet_old)) {
    return {
      ...patch,
      title_old: patch.title_old ?? exp.title,
      new_title: neu,
      bullet_old: undefined,
      bullet_new: undefined,
    };
  }

  // Dates-only: bullet_old equals current dates line (rare but seen in the wild)
  if (old === exp.dates.trim()) {
    return {
      ...patch,
      dates_old: patch.dates_old ?? exp.dates,
      new_dates: neu,
      bullet_old: undefined,
      bullet_new: undefined,
    };
  }

  return patch;
}

/** Apply a single chat patch to a tailored resume copy. Returns applied=false when nothing matched. */
export function applyResumePatch(
  tailored: TailoredResumeOutput,
  patch: ResumePatch,
): ApplyResumePatchResult {
  const updated = structuredClone(tailored);
  let applied = false;

  if (patch.section === "summary" && patch.new_summary?.trim()) {
    updated.summary = patch.new_summary.trim();
    applied = true;
  }

  if (patch.section === "skills") {
    let skills = [...(updated.skills ?? [])];
    let changed = false;
    if (patch.add_skills?.length) {
      const toAdd = patch.add_skills.filter((s) => !skills.includes(s));
      if (toAdd.length) {
        skills = [...skills, ...toAdd];
        changed = true;
      }
    }
    if (patch.remove_skills?.length) {
      const removeSet = new Set(patch.remove_skills);
      const next = skills.filter((s) => !removeSet.has(s));
      if (next.length !== skills.length) {
        skills = next;
        changed = true;
      }
    }
    if (changed) {
      updated.skills = skills;
      applied = true;
    }
  }

  if (patch.section === "experience" && patch.company?.trim()) {
    const idx = findExperienceIndex(updated.experience, patch.company);
    if (idx >= 0) {
      const exp = updated.experience[idx]!;
      const coerced = coerceExperiencePatch(exp, patch);
      let anyChange = false;
      const next = { ...exp };

      if (coerced.bullet_old && coerced.bullet_new) {
        const matched = exp.bullets.some((b) => b === coerced.bullet_old);
        if (matched) {
          next.bullets = exp.bullets.map((b) =>
            b === coerced.bullet_old ? coerced.bullet_new! : b,
          );
          anyChange = true;
        }
      }

      if (coerced.new_title?.trim()) {
        next.title = coerced.new_title.trim();
        anyChange = true;
      }

      if (coerced.new_dates?.trim()) {
        next.dates = coerced.new_dates.trim();
        anyChange = true;
      }

      if (anyChange) {
        updated.experience = updated.experience.map((e, i) => (i === idx ? next : e));
        applied = true;
      } else {
        return {
          updated,
          applied: false,
          failureReason: "Company matched but bullet, title, or dates did not match.",
        };
      }
    } else {
      return {
        updated,
        applied: false,
        failureReason: "Company name did not match any experience entry.",
      };
    }
  }

  if (patch.section === "projects") {
    const before = updated.projects ?? [];

    // Remove projects
    if ((patch.remove_projects?.length ?? 0) > 0) {
      const toRemove = patch.remove_projects!;
      const next = before.filter((proj) => {
        const name = projectDisplayName(proj as Record<string, unknown>);
        return !toRemove.some((target) => matchProjectName(name, target));
      });
      if (next.length < before.length) {
        updated.projects = next;
        applied = true;
      } else {
        return {
          updated,
          applied: false,
          failureReason: "No project names matched — use exact names from the resume.",
        };
      }
    }

    // Edit bullets in a specific project
    if (patch.project_name?.trim()) {
      const projIdx = before.findIndex((p) =>
        matchProjectName(projectDisplayName(p as Record<string, unknown>), patch.project_name!),
      );
      if (projIdx < 0) {
        return {
          updated,
          applied: false,
          failureReason: `Project "${patch.project_name}" not found — copy the name exactly from the resume.`,
        };
      }

      const proj = { ...(before[projIdx] as Record<string, unknown>) };
      const bullets = Array.isArray(proj.bullets) ? [...(proj.bullets as string[])] : [];

      // Replace all bullets at once
      if (
        (patch.project_bullets_replace_all?.length ?? 0) > 0 &&
        !patch.project_bullet_old?.trim()
      ) {
        proj.bullets = patch.project_bullets_replace_all!;
        updated.projects = before.map((p, i) => (i === projIdx ? proj : p));
        applied = true;
      } else if (patch.project_bullet_old?.trim() && patch.project_bullet_new?.trim()) {
        // Replace a single bullet — fuzzy match on leading ~60 chars
        const oldText = patch.project_bullet_old.trim();
        const matchIdx = bullets.findIndex(
          (b) => b === oldText || b.startsWith(oldText.slice(0, 60)),
        );
        if (matchIdx < 0) {
          return {
            updated,
            applied: false,
            failureReason: "Bullet text did not match any bullet in this project.",
          };
        }
        bullets[matchIdx] = patch.project_bullet_new.trim();
        proj.bullets = bullets;
        updated.projects = before.map((p, i) => (i === projIdx ? proj : p));
        applied = true;
      }
    }
  }

  return { updated, applied };
}
