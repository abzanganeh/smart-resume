import type {
  ResumePatch,
  TailoredEducation,
  TailoredExperience,
  TailoredResumeOutput,
} from "@/lib/api";

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

function normalizeOrgKey(name: string): string {
  return name
    .toLowerCase()
    .replace(/[/\\|]/g, " ")
    .replace(/[—–\-]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function editDistance(a: string, b: string): number {
  if (a === b) return 0;
  const rows = a.length + 1;
  const cols = b.length + 1;
  const matrix = Array.from({ length: rows }, () => Array<number>(cols).fill(0));
  for (let i = 0; i < rows; i++) matrix[i]![0] = i;
  for (let j = 0; j < cols; j++) matrix[0]![j] = j;
  for (let i = 1; i < rows; i++) {
    for (let j = 1; j < cols; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      matrix[i]![j] = Math.min(
        matrix[i - 1]![j]! + 1,
        matrix[i]![j - 1]! + 1,
        matrix[i - 1]![j - 1]! + cost,
      );
    }
  }
  return matrix[rows - 1]![cols - 1]!;
}

/** Case-insensitive org match (handles typos like Accptto vs Acceptto). */
export function matchExperienceCompany(
  entryCompany: string,
  patchCompany: string,
): boolean {
  return matchOrgName(entryCompany, patchCompany);
}

export function matchEducationInstitution(
  entryInstitution: string,
  patchInstitution: string,
): boolean {
  return matchOrgName(entryInstitution, patchInstitution);
}

function matchOrgName(actual: string, patch: string): boolean {
  const a = normalizeOrgKey(actual);
  const b = normalizeOrgKey(patch);
  if (!a || !b) return false;
  if (a === b) return true;
  if (a.includes(b) || b.includes(a)) return true;

  const aHead = a.split(" ")[0] ?? a;
  const bHead = b.split(" ")[0] ?? b;
  if (aHead.length >= 4 && bHead.length >= 4 && editDistance(aHead, bHead) <= 2) {
    return true;
  }
  if (a.length >= 5 && b.length >= 5 && editDistance(a, b) <= 3) {
    return true;
  }
  return false;
}

function findExperienceIndex(
  experience: TailoredExperience[],
  patchCompany: string,
): number {
  return experience.findIndex((exp) => matchExperienceCompany(exp.company, patchCompany));
}

function findEducationIndex(
  education: TailoredEducation[],
  patchInstitution: string,
): number {
  return education.findIndex((edu) =>
    matchEducationInstitution(edu.institution, patchInstitution),
  );
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

/** Split "Title — subtitle" into short name + optional description. */
function splitProjectTitle(rawName: string): { name: string; description?: string } {
  const trimmed = rawName.trim();
  const dashParts = trimmed.split(/[—–|]/);
  if (dashParts.length > 1) {
    const head = dashParts[0]?.trim() ?? trimmed;
    const tail = dashParts.slice(1).join("—").trim();
    return tail ? { name: head, description: tail } : { name: head };
  }

  const words = trimmed.split(/\s+/);
  if (words.length <= 4) return { name: trimmed };

  return {
    name: words.slice(0, 3).join(" "),
    description: words.slice(3).join(" "),
  };
}

/** Match education entry referenced in a description-only LLM patch. */
export function inferEducationInstitution(
  education: TailoredEducation[],
  patch: ResumePatch,
): TailoredEducation | undefined {
  if (patch.section !== "education") return undefined;

  if (patch.institution?.trim()) {
    const idx = findEducationIndex(education, patch.institution);
    if (idx >= 0) return education[idx];
  }

  const haystack = `${patch.description ?? ""} ${patch.institution ?? ""}`.toLowerCase();

  for (const edu of education) {
    const inst = edu.institution.toLowerCase();
    if (inst && haystack.includes(inst)) return edu;
    if (haystack.includes("kickstart") && inst.includes("kickstart")) return edu;
    if ((haystack.includes(" ik") || haystack.includes("to ik")) && inst === "ik") return edu;
    const degree = edu.degree.toLowerCase();
    if (degree.length > 8 && haystack.includes(degree.slice(0, 16))) return edu;
  }

  if (haystack.includes("kickstart")) {
    return education.find((e) => e.institution.toLowerCase().includes("kickstart"));
  }
  if (haystack.includes(" ik") || /\bik\b/.test(haystack)) {
    return education.find((e) => e.institution.toLowerCase() === "ik");
  }
  if (haystack.includes("capstone")) {
    return (
      education.find((e) => e.institution.toLowerCase().includes("kickstart")) ??
      education.find((e) => e.degree.toLowerCase().includes("aiml")) ??
      (education.length === 1 ? education[0] : undefined)
    );
  }

  return undefined;
}

function extractCapstoneBullet(description: string): string {
  const match = description.match(/capstone[^.;\n]*(?:800\s*\/?\s*800)?[^.;\n]*/i);
  if (match) {
    return match[0]
      .trim()
      .replace(/^(add(ed)?|include)\s+/i, "")
      .replace(/^bullet:\s*/i, "");
  }
  return "Capstone project — scored 800/800";
}

/** LLMs often emit education patches with only description — infer institution and fields. */
export function coerceEducationPatch(
  education: TailoredEducation[],
  patch: ResumePatch,
): ResumePatch {
  if (patch.section !== "education") return patch;

  const matched = inferEducationInstitution(education, patch);
  const institution = patch.institution?.trim() || matched?.institution;
  if (!institution) return patch;

  const desc = (patch.description ?? "").toLowerCase();
  let newInstitution = patch.new_institution?.trim();

  if (
    !newInstitution &&
    (desc.includes("to ik") ||
      desc.includes("rename") && desc.includes("ik") ||
      (desc.includes("interview kickstart") && desc.includes("ik")))
  ) {
    newInstitution = "IK";
  }

  let addBullets = [...(patch.add_education_bullets ?? [])];
  if (
    addBullets.length === 0 &&
    (desc.includes("capstone") || desc.includes("800/800") || desc.includes("800"))
  ) {
    addBullets = [extractCapstoneBullet(patch.description ?? "")];
  }

  const hasAction =
    !!newInstitution ||
    addBullets.length > 0 ||
    !!patch.new_degree?.trim() ||
    (!!patch.education_bullet_old?.trim() && !!patch.education_bullet_new?.trim());

  if (!hasAction && !patch.institution?.trim()) {
    return { ...patch, institution };
  }

  return {
    ...patch,
    institution,
    ...(newInstitution ? { new_institution: newInstitution } : {}),
    ...(addBullets.length ? { add_education_bullets: addBullets } : {}),
  };
}

export function normalizeResumePatch(
  tailored: TailoredResumeOutput,
  patch: ResumePatch,
): ResumePatch {
  if (patch.section === "projects") {
    return coerceProjectsPatch(tailored.projects ?? [], patch);
  }
  if (patch.section === "education") {
    return coerceEducationPatch(tailored.education, patch);
  }
  return patch;
}

/** LLMs often use project_name + replace_all when they mean add a new project. */
export function coerceProjectsPatch(
  projects: Record<string, unknown>[],
  patch: ResumePatch,
): ResumePatch {
  if (patch.section !== "projects") return patch;
  if (patch.new_project?.name?.trim()) return patch;
  if (!patch.project_name?.trim()) return patch;
  if ((patch.project_bullets_replace_all?.length ?? 0) === 0) return patch;

  const exists = projects.some((p) =>
    matchProjectName(projectDisplayName(p), patch.project_name!),
  );
  if (exists) return patch;

  const { name, description } = splitProjectTitle(patch.project_name);
  return {
    ...patch,
    project_name: undefined,
    project_bullets_replace_all: undefined,
    new_project: {
      name,
      description,
      bullets: patch.project_bullets_replace_all!,
    },
  };
}

/** Apply a single chat patch to a tailored resume copy. Returns applied=false when nothing matched. */
export function applyResumePatch(
  tailored: TailoredResumeOutput,
  patch: ResumePatch,
): ApplyResumePatchResult {
  const updated = structuredClone(tailored);
  const effectivePatch = normalizeResumePatch(updated, patch);
  let applied = false;

  if (effectivePatch.section === "contact" && effectivePatch.new_name?.trim()) {
    updated.contact = {
      ...(updated.contact ?? {}),
      name: effectivePatch.new_name.trim(),
    };
    applied = true;
  }

  if (effectivePatch.section === "summary" && effectivePatch.new_summary?.trim()) {
    updated.summary = effectivePatch.new_summary.trim();
    applied = true;
  }

  if (effectivePatch.section === "skills") {
    let skills = [...(updated.skills ?? [])];
    let changed = false;
    if (effectivePatch.add_skills?.length) {
      const toAdd = effectivePatch.add_skills.filter((s) => !skills.includes(s));
      if (toAdd.length) {
        skills = [...skills, ...toAdd];
        changed = true;
      }
    }
    if (effectivePatch.remove_skills?.length) {
      const removeSet = new Set(effectivePatch.remove_skills);
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

  if (effectivePatch.section === "experience" && effectivePatch.company?.trim()) {
    const idx = findExperienceIndex(updated.experience, effectivePatch.company);
    if (idx >= 0) {
      if (effectivePatch.delete_experience) {
        updated.experience = updated.experience.filter((_, i) => i !== idx);
        return { updated, applied: true };
      }

      const exp = updated.experience[idx]!;
      const coerced = coerceExperiencePatch(exp, effectivePatch);
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

  if (effectivePatch.section === "education" && effectivePatch.institution?.trim()) {
    const idx = findEducationIndex(updated.education, effectivePatch.institution);
    if (idx < 0) {
      return {
        updated,
        applied: false,
        failureReason: "Institution name did not match any education entry.",
      };
    }

    const edu = updated.education[idx]!;
    const next = { ...edu };
    let anyChange = false;

    if (effectivePatch.new_institution?.trim()) {
      next.institution = effectivePatch.new_institution.trim();
      anyChange = true;
    }
    if (effectivePatch.new_degree?.trim()) {
      next.degree = effectivePatch.new_degree.trim();
      anyChange = true;
    }
    if (effectivePatch.add_education_bullets?.length) {
      const toAdd = effectivePatch.add_education_bullets.filter(
        (b) => !next.bullets.includes(b),
      );
      if (toAdd.length) {
        next.bullets = [...next.bullets, ...toAdd];
        anyChange = true;
      }
    }
    if (effectivePatch.education_bullet_old?.trim() && effectivePatch.education_bullet_new?.trim()) {
      const oldText = effectivePatch.education_bullet_old.trim();
      const matched = next.bullets.some((b) => b === oldText);
      if (matched) {
        next.bullets = next.bullets.map((b) =>
          b === oldText ? effectivePatch.education_bullet_new!.trim() : b,
        );
        anyChange = true;
      }
    }

    if (anyChange) {
      updated.education = updated.education.map((e, i) => (i === idx ? next : e));
      applied = true;
    } else {
      return {
        updated,
        applied: false,
        failureReason: "Institution matched but no education fields changed.",
      };
    }
  }

  if (effectivePatch.section === "certifications") {
    let certs = [...(updated.certifications ?? [])];
    let changed = false;
    if (effectivePatch.remove_certifications?.length) {
      const removeSet = new Set(effectivePatch.remove_certifications);
      const next = certs.filter((c) => !removeSet.has(c));
      if (next.length !== certs.length) {
        certs = next;
        changed = true;
      }
    }
    if (effectivePatch.add_certifications?.length) {
      const toAdd = effectivePatch.add_certifications.filter((c) => !certs.includes(c));
      if (toAdd.length) {
        certs = [...certs, ...toAdd];
        changed = true;
      }
    }
    if (changed) {
      updated.certifications = certs;
      applied = true;
    } else if (
      (effectivePatch.remove_certifications?.length ?? 0) > 0 ||
      (effectivePatch.add_certifications?.length ?? 0) > 0
    ) {
      return {
        updated,
        applied: false,
        failureReason: "No matching certifications found to add or remove.",
      };
    }
  }

  if (effectivePatch.section === "projects" && effectivePatch.new_project?.name?.trim()) {
    const newName = effectivePatch.new_project.name.trim();
    const exists = (updated.projects ?? []).some((proj) =>
      matchProjectName(projectDisplayName(proj as Record<string, unknown>), newName),
    );
    if (exists) {
      return {
        updated,
        applied: false,
        failureReason: `"${newName}" already exists — edit the existing project or delete duplicates first.`,
      };
    }
    updated.projects = [...(updated.projects ?? []), effectivePatch.new_project];
    applied = true;
  }

  if (effectivePatch.section === "projects" && !effectivePatch.new_project) {
    const before = updated.projects ?? [];

    // Remove projects
    if ((effectivePatch.remove_projects?.length ?? 0) > 0) {
      const toRemove = effectivePatch.remove_projects!;
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
    if (effectivePatch.project_name?.trim()) {
      const projIdx = before.findIndex((p) =>
        matchProjectName(
          projectDisplayName(p as Record<string, unknown>),
          effectivePatch.project_name!,
        ),
      );
      if (projIdx < 0) {
        return {
          updated,
          applied: false,
          failureReason: `Project "${effectivePatch.project_name}" not found — copy the name exactly from the resume.`,
        };
      }

      const proj = { ...(before[projIdx] as Record<string, unknown>) };

      if (effectivePatch.new_project_title?.trim()) {
        proj.name = effectivePatch.new_project_title.trim();
        applied = true;
      }
      if (effectivePatch.new_project_description != null) {
        proj.description = effectivePatch.new_project_description.trim();
        applied = true;
      }

      const bullets = Array.isArray(proj.bullets) ? [...(proj.bullets as string[])] : [];

      // Replace all bullets at once
      if (
        (effectivePatch.project_bullets_replace_all?.length ?? 0) > 0 &&
        !effectivePatch.project_bullet_old?.trim()
      ) {
        proj.bullets = effectivePatch.project_bullets_replace_all!;
        updated.projects = before.map((p, i) => (i === projIdx ? proj : p));
        applied = true;
      } else if (
        effectivePatch.project_bullet_old?.trim() &&
        effectivePatch.project_bullet_new?.trim()
      ) {
        // Replace a single bullet — fuzzy match on leading ~60 chars
        const oldText = effectivePatch.project_bullet_old.trim();
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
        bullets[matchIdx] = effectivePatch.project_bullet_new.trim();
        proj.bullets = bullets;
        updated.projects = before.map((p, i) => (i === projIdx ? proj : p));
        applied = true;
      } else if (
        effectivePatch.new_project_title?.trim() ||
        effectivePatch.new_project_description != null
      ) {
        updated.projects = before.map((p, i) => (i === projIdx ? proj : p));
      }
    }
  }

  return { updated, applied };
}
