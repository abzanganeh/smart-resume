import { applyResumePatch, coerceEducationPatch } from "@/lib/applyResumePatch";
import type { ResumePatch, TailoredResumeOutput } from "@/lib/api";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

const base: TailoredResumeOutput = {
  contact: {},
  summary: "Summary",
  skills: ["Python"],
  experience: [
    {
      title: "Senior Software Engineer",
      company: "SecureAuth",
      dates: "2021 – 2024",
      bullets: ["Led identity systems."],
      keywords_injected: [],
      removed_bullets: [],
    },
    {
      title: "Software Engineer",
      company: "Acceptto",
      dates: "2019 – 2021",
      bullets: ["Built MFA flows."],
      keywords_injected: [],
      removed_bullets: [],
    },
  ],
  education: [],
  projects: [],
  certifications: [],
  rewrite_notes: [],
  metrics_needed: [],
};

function runTests() {
  console.log("\napplyResumePatch tests\n");

  const datesPatch: ResumePatch = {
    section: "experience",
    company: "SecureAuth",
    description: "Fix SecureAuth dates",
    new_dates: "2022 – 2025",
  };
  const datesResult = applyResumePatch(base, datesPatch);
  assert(datesResult.applied, "dates patch applies when company matches");
  assert(
    datesResult.updated.experience[0]?.dates === "2022 – 2025",
    "SecureAuth dates updated",
  );
  assert(
    datesResult.updated.experience[1]?.dates === "2019 – 2021",
    "other companies unchanged",
  );

  const titlePatch: ResumePatch = {
    section: "experience",
    company: "Acceptto",
    description: "Rename title",
    new_title: "Staff Software Engineer",
  };
  const titleResult = applyResumePatch(base, titlePatch);
  assert(titleResult.applied, "title patch applies when company matches");
  assert(
    titleResult.updated.experience[1]?.title === "Staff Software Engineer",
    "Acceptto title updated",
  );

  const bulletPatch: ResumePatch = {
    section: "experience",
    company: "Acceptto",
    description: "Stronger bullet",
    bullet_old: "Built MFA flows.",
    bullet_new: "Built MFA flows with metrics.",
  };
  const bulletResult = applyResumePatch(base, bulletPatch);
  assert(bulletResult.applied, "bullet patch applies when bullet_old matches");
  assert(
    bulletResult.updated.experience[1]?.bullets[0] === "Built MFA flows with metrics.",
    "bullet text replaced",
  );

  const missPatch: ResumePatch = {
    section: "experience",
    company: "Unknown Corp",
    description: "noop",
    new_dates: "2020 – 2022",
  };
  const missResult = applyResumePatch(base, missPatch);
  assert(!missResult.applied, "unknown company returns applied=false");
  assert(
    JSON.stringify(missResult.updated) === JSON.stringify(base),
    "resume unchanged when patch misses",
  );

  const legacyTitlePatch: ResumePatch = {
    section: "experience",
    company: "SecureAuth",
    description: "Title via bullet fields",
    bullet_old: "Senior Software Engineer",
    bullet_new: "Senior Software Engineer (2022 – 2025)",
  };
  const legacyResult = applyResumePatch(base, legacyTitlePatch);
  assert(legacyResult.applied, "legacy title-as-bullet patch applies");
  assert(
    legacyResult.updated.experience[0]?.title === "Senior Software Engineer (2022 – 2025)",
    "title updated from legacy bullet patch",
  );

  const withProjects: TailoredResumeOutput = {
    ...base,
    projects: [
      { name: "ENTROS — Mobile Companion for Asar", bullets: ["Built pairing."] },
      { name: "TRUST MOBILE — Mobile Companion for Trust/Kia", bullets: ["MFA flows."] },
      { name: "RAI — Agentic AI", bullets: ["RAG pipeline."] },
    ],
  };
  const removeProjectsPatch: ResumePatch = {
    section: "projects",
    description: "Remove mobile companion projects",
    remove_projects: ["Entros", "Trust Mobile"],
  };
  const projectsResult = applyResumePatch(withProjects, removeProjectsPatch);
  assert(projectsResult.applied, "project removal applies with fuzzy names");
  assert(projectsResult.updated.projects.length === 1, "two projects removed");
  assert(
    projectDisplayName(projectsResult.updated.projects[0] as Record<string, unknown>) === "RAI — Agentic AI",
    "unmatched project kept",
  );

  const withBullets: TailoredResumeOutput = {
    ...base,
    projects: [
      {
        name: "TRUST (Kia + Trace + Dashboard)",
        bullets: [
          "Designed multi-service IAM architecture (Kia, Trace, Dashboard).",
          "Built 12+ API surfaces (device JWT v10, OAuth2/OIDC, SCIM).",
        ],
      },
    ],
  };

  const replaceAllPatch: ResumePatch = {
    section: "projects",
    description: "Replace all TRUST bullets with quantified versions",
    project_name: "TRUST (Kia + Trace + Dashboard)",
    project_bullets_replace_all: [
      "Designed 3-service IAM architecture supporting 5+ enterprise tenants.",
      "Built 12+ API surfaces reducing onboarding time by ~30%.",
    ],
  };
  const replaceAllResult = applyResumePatch(withBullets, replaceAllPatch);
  assert(replaceAllResult.applied, "project replace-all bullets applies");
  const trustProj = replaceAllResult.updated.projects[0] as Record<string, unknown>;
  assert(
    (trustProj.bullets as string[])[0]?.includes("3-service"),
    "replace-all first bullet updated",
  );
  assert((trustProj.bullets as string[]).length === 2, "replace-all bullet count correct");

  const replaceSinglePatch: ResumePatch = {
    section: "projects",
    description: "Replace one TRUST bullet",
    project_name: "TRUST (Kia + Trace + Dashboard)",
    project_bullet_old: "Designed multi-service IAM architecture (Kia, Trace, Dashboard).",
    project_bullet_new: "Designed 3-service IAM architecture supporting 5+ enterprise tenants.",
  };
  const replaceSingleResult = applyResumePatch(withBullets, replaceSinglePatch);
  assert(replaceSingleResult.applied, "project single-bullet replace applies");
  const trustSingle = replaceSingleResult.updated.projects[0] as Record<string, unknown>;
  assert(
    (trustSingle.bullets as string[])[0]?.includes("3-service"),
    "single bullet replaced",
  );

  const addProjectPatch: ResumePatch = {
    section: "projects",
    description: "Add Fraud Shield AI project",
    new_project: {
      name: "Fraud Shield AI",
      description: "End-to-end credit card fraud detection pipeline",
      bullets: ["Built PySpark feature pipeline.", "Deployed Streamlit inference app."],
    },
  };
  const addProjectResult = applyResumePatch(base, addProjectPatch);
  assert(addProjectResult.applied, "new_project patch appends project");
  assert(addProjectResult.updated.projects.length === 1, "one project added");
  assert(
    projectDisplayName(addProjectResult.updated.projects[0] as Record<string, unknown>) ===
      "Fraud Shield AI",
    "new project name stored",
  );

  const duplicateProjectPatch: ResumePatch = {
    section: "projects",
    description: "Duplicate Fraud Shield AI",
    new_project: {
      name: "Fraud Shield AI",
      bullets: ["Duplicate entry."],
    },
  };
  const duplicateProjectResult = applyResumePatch(addProjectResult.updated, duplicateProjectPatch);
  assert(!duplicateProjectResult.applied, "duplicate new_project rejected");
  assert(
    duplicateProjectResult.updated.projects.length === 1,
    "no second Fraud Shield AI appended",
  );

  const mislabeledAddPatch: ResumePatch = {
    section: "projects",
    description: "Add project via wrong LLM fields",
    project_name: "Fraud Shield AI End-to-end credit card fraud detection pipeline",
    project_bullets_replace_all: [
      "Built end-to-end fraud detection pipeline with PySpark preprocessing.",
      "Deployed Streamlit inference app for batch scoring.",
    ],
  };
  const mislabeledAddResult = applyResumePatch(base, mislabeledAddPatch);
  assert(mislabeledAddResult.applied, "mislabeled add patch coerces to new_project");
  assert(mislabeledAddResult.updated.projects.length === 1, "coerced add creates one project");
  const coercedProj = mislabeledAddResult.updated.projects[0] as Record<string, unknown>;
  assert(
    projectDisplayName(coercedProj) === "Fraud Shield AI",
    "coerced project uses short title",
  );
  assert((coercedProj.bullets as string[]).length === 2, "coerced project keeps bullets");

  const typoDatesPatch: ResumePatch = {
    section: "experience",
    company: "Accptto",
    description: "Fix Acceptto dates",
    new_dates: "2016 – 2022",
  };
  const typoDatesResult = applyResumePatch(base, typoDatesPatch);
  assert(typoDatesResult.applied, "fuzzy company typo Accptto matches Acceptto");
  assert(
    typoDatesResult.updated.experience[1]?.dates === "2016 – 2022",
    "typo company dates updated",
  );

  const withEducation: TailoredResumeOutput = {
    ...base,
    education: [
      {
        degree: "AIML Software Engineering Program",
        institution: "Interview Kickstart",
        year: "",
        bullets: [],
      },
    ],
  };
  const descriptionOnlyPatch: ResumePatch = {
    section: "education",
    description: "Changed Interview Kickstart to IK in education",
  };
  const coercedDesc = coerceEducationPatch(
    withEducation.education,
    descriptionOnlyPatch,
  );
  assert(coercedDesc.institution === "Interview Kickstart", "coerce finds institution from description");
  assert(coercedDesc.new_institution === "IK", "coerce infers IK rename from description");

  const capstoneOnlyPatch: ResumePatch = {
    section: "education",
    description: "Added capstone project with a perfect score of 800/800",
  };
  const coercedCapstone = coerceEducationPatch(withEducation.education, capstoneOnlyPatch);
  assert(
    (coercedCapstone.add_education_bullets?.length ?? 0) > 0,
    "coerce infers capstone bullet from description",
  );

  const descApplyResult = applyResumePatch(withEducation, descriptionOnlyPatch);
  assert(descApplyResult.applied, "description-only education rename applies end-to-end");
  assert(
    descApplyResult.updated.education[0]?.institution === "IK",
    "description-only patch renames institution",
  );

  const eduRenamePatch: ResumePatch = {
    section: "education",
    institution: "Interview Kickstart",
    description: "Rename to IK",
    new_institution: "IK",
  };
  const eduRenameResult = applyResumePatch(withEducation, eduRenamePatch);
  assert(eduRenameResult.applied, "education institution rename applies");
  assert(
    eduRenameResult.updated.education[0]?.institution === "IK",
    "institution renamed to IK",
  );

  const eduBulletPatch: ResumePatch = {
    section: "education",
    institution: "IK",
    description: "Add capstone bullet",
    add_education_bullets: ["Capstone project: scored 800/800 on final evaluation."],
  };
  const eduBulletResult = applyResumePatch(eduRenameResult.updated, eduBulletPatch);
  assert(eduBulletResult.applied, "education bullet add applies");
  assert(
    eduBulletResult.updated.education[0]?.bullets.length === 1,
    "one education bullet added",
  );

  console.log("\nAll applyResumePatch tests passed.\n");
}

function projectDisplayName(project: Record<string, unknown>): string {
  return String(project.name ?? "").trim();
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("applyResumePatch.test.ts")) {
  runTests();
}

export { runTests };
