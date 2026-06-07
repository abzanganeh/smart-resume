import { applyResumePatch } from "@/lib/applyResumePatch";
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

  console.log("\nAll applyResumePatch tests passed.\n");
}

function projectDisplayName(project: Record<string, unknown>): string {
  return String(project.name ?? "").trim();
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("applyResumePatch.test.ts")) {
  runTests();
}

export { runTests };
