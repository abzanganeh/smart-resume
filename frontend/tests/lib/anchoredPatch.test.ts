import assert from "node:assert/strict";
import test from "node:test";

import {
  buildBatchChatMessage,
  enrichIssuesWithInferredAnchors,
  hydratePatchFromAnchor,
  hydratePatchesFromIssues,
  inferAnchorFromIssue,
  matchAnchorForPatch,
  resolveBulletAtAnchor,
} from "@/lib/anchoredPatch";
import { applyResumePatch } from "@/lib/applyResumePatch";
import { isPatchPlaceable } from "@/lib/suggestionHighlight";
import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";

const tailored: TailoredResumeOutput = {
  contact: { name: "Ali" },
  summary: "Summary",
  skills: [],
  experience: [],
  education: [],
  projects: [
    {
      name: "Flint — Meeting Co-Pilot",
      bullets: ["Local-first AI desktop co-pilot with Whisper transcription and on-device RAG."],
    },
  ],
  certifications: [],
  rewrite_notes: [],
  metrics_needed: [],
};

const anchoredIssue: BlockingIssue = {
  category: "bullet",
  description: "Strong action verbs",
  suggestion: "Open with a stronger verb: Championed local-first AI desktop co-pilot…",
  impact: "medium",
  fix_effort: "manual_rewrite",
  anchor: { section: "projects", entry_index: 0, bullet_index: 0 },
};

test("resolveBulletAtAnchor reads live project bullet", () => {
  const resolved = resolveBulletAtAnchor(tailored, anchoredIssue.anchor!);
  assert.ok(resolved);
  assert.equal(resolved.project_name, "Flint — Meeting Co-Pilot");
  assert.match(resolved.project_bullet_old ?? "", /Local-first AI desktop co-pilot/);
});

test("hydratePatchFromAnchor replaces wrong LLM bullet_old", () => {
  const hydrated = hydratePatchFromAnchor(tailored, {
    section: "projects",
    description: "Rewrite bullet",
    project_name: "Flint",
    project_bullet_old: "Open with a stronger verb: Championed…",
    project_bullet_new: "Engineered local-first AI desktop co-pilot with Whisper transcription and on-device RAG.",
  }, anchoredIssue.anchor);
  assert.equal(hydrated.project_name, "Flint — Meeting Co-Pilot");
  assert.match(hydrated.project_bullet_old ?? "", /Local-first AI desktop co-pilot/);
  assert.ok(isPatchPlaceable(hydrated, tailored));
});

test("applyResumePatch uses anchor index when bullet_old is missing", () => {
  const patch = hydratePatchFromAnchor(
    tailored,
    {
      section: "projects",
      description: "Rewrite bullet",
      project_bullet_new: "Engineered local-first AI desktop co-pilot with Whisper transcription and on-device RAG.",
      anchor: anchoredIssue.anchor,
    },
    anchoredIssue.anchor,
  );
  const result = applyResumePatch(tailored, patch);
  assert.equal(result.applied, true);
  assert.match(
    (result.updated.projects[0] as { bullets: string[] }).bullets[0],
    /^Engineered local-first/,
  );
});

test("applyResumePatch refuses anchor apply when bullet_old is wrong", () => {
  const patch = {
    section: "projects" as const,
    description: "Rewrite bullet",
    project_bullet_old: "Totally wrong stale bullet text.",
    project_bullet_new: "Should not apply via anchor.",
    anchor: anchoredIssue.anchor,
  };
  const result = applyResumePatch(tailored, patch);
  assert.equal(result.applied, false);
  assert.deepEqual(result.updated, tailored);
  assert.equal(isPatchPlaceable(patch, tailored), false);
});

test("matchAnchorForPatch refuses ambiguous Flint project names", () => {
  const ambiguous: TailoredResumeOutput = {
    ...tailored,
    projects: [
      { name: "FlintApply", bullets: ["Resume tailoring."] },
      { name: "FlintGuide", bullets: ["Interview co-pilot."] },
    ],
  };
  const issues: BlockingIssue[] = [
    {
      ...anchoredIssue,
      anchor: { section: "projects", entry_index: 0, bullet_index: 0 },
    },
    {
      ...anchoredIssue,
      description: "Second Flint project",
      anchor: { section: "projects", entry_index: 1, bullet_index: 0 },
    },
  ];
  const patch = {
    section: "projects" as const,
    description: "Rewrite bullet",
    project_name: "Flint",
    project_bullet_new: "Should not bind.",
  };
  assert.equal(matchAnchorForPatch(ambiguous, patch, issues), null);
});

test("resolveBulletAtAnchor returns null for out-of-range index", () => {
  assert.equal(
    resolveBulletAtAnchor(tailored, {
      section: "projects",
      entry_index: 9,
      bullet_index: 0,
    }),
    null,
  );
  assert.equal(
    resolveBulletAtAnchor(tailored, {
      section: "projects",
      entry_index: 0,
      bullet_index: 9,
    }),
    null,
  );
});

test("hydratePatchesFromIssues ignores unknown LLM anchor", () => {
  const hydrated = hydratePatchesFromIssues(
    tailored,
    [
      {
        section: "projects",
        description: "Rewrite bullet",
        project_bullet_new: "Injected rewrite.",
        anchor: { section: "projects", entry_index: 0, bullet_index: 0 },
      },
    ],
    [],
  )[0];
  assert.equal(hydrated.project_bullet_old, undefined);
});

test("inferAnchorFromIssue resolves bullet-too-short suggestions", () => {
  const withExperience: TailoredResumeOutput = {
    ...tailored,
    experience: [
      {
        title: "Engineer",
        company: "Northwind Payments",
        dates: "2022 – 2024",
        bullets: ["Mentored 3 engineers on code review standards and on-call practices."],
        removed_bullets: [],
        keywords_injected: [],
      },
    ],
  };
  const issue: BlockingIssue = {
    category: "bullet",
    description: "Bullet length sweet spot (12-25 words)",
    suggestion:
      "Bullet too short (10 words): Mentored 3 engineers on code review standards and on-call practices.",
    impact: "medium",
    fix_effort: "manual_rewrite",
  };
  const anchor = inferAnchorFromIssue(withExperience, issue);
  assert.deepEqual(anchor, { section: "experience", entry_index: 0, bullet_index: 0 });
  assert.deepEqual(
    enrichIssuesWithInferredAnchors(withExperience, [issue])[0]!.anchor,
    anchor,
  );
});

test("hydratePatchesFromIssues positional bind fixes invented JD company", () => {
  const withExperience: TailoredResumeOutput = {
    ...tailored,
    experience: [
      {
        title: "Software Engineer",
        company: "LedgerFlow",
        dates: "2022 – 2024",
        bullets: ["Led AWS migration for payment processing platform."],
        removed_bullets: [],
        keywords_injected: [],
      },
    ],
  };
  const metricIssue: BlockingIssue = {
    category: "metric",
    description: "Add a metric to AWS migration bullet",
    suggestion: "Add a quantified outcome such as reduced migration time by 35%.",
    impact: "medium",
    fix_effort: "user_input",
    anchor: { section: "experience", entry_index: 0, bullet_index: 0 },
  };
  const hydrated = hydratePatchesFromIssues(
    withExperience,
    [
      {
        section: "experience",
        description: "Add quantifiable metric to AWS migration bullet",
        company: "Northwind Payments",
        bullet_old: "Wrong bullet.",
        bullet_new: "Led AWS migration for payment processing platform, reducing cutover time by 35%.",
      },
    ],
    [metricIssue],
  )[0]!;
  assert.equal(hydrated.company, "LedgerFlow");
  assert.match(hydrated.bullet_old ?? "", /Led AWS migration/);
  assert.equal(isPatchPlaceable(hydrated, withExperience), true);
});

test("hydratePatchesFromIssues swapped companies do not mis-bind", () => {
  const withTwoCompanies: TailoredResumeOutput = {
    ...tailored,
    experience: [
      {
        title: "Engineer",
        company: "Acme Corp",
        dates: "2020 – 2022",
        bullets: ["Built APIs for payments."],
        removed_bullets: [],
        keywords_injected: [],
      },
      {
        title: "Engineer",
        company: "Northwind Payments",
        dates: "2022 – 2024",
        bullets: ["Led AWS migration for payment processing platform."],
        removed_bullets: [],
        keywords_injected: [],
      },
    ],
  };
  const issues: BlockingIssue[] = [
    {
      category: "metric",
      description: "Acme metric",
      suggestion: "Add metric.",
      impact: "medium",
      fix_effort: "user_input",
      anchor: { section: "experience", entry_index: 0, bullet_index: 0 },
    },
    {
      category: "metric",
      description: "Northwind metric",
      suggestion: "Add metric.",
      impact: "medium",
      fix_effort: "user_input",
      anchor: { section: "experience", entry_index: 1, bullet_index: 0 },
    },
  ];
  const hydrated = hydratePatchesFromIssues(
    withTwoCompanies,
    [
      {
        section: "experience",
        description: "Northwind fix",
        company: "Northwind Payments",
        bullet_old: "Led AWS migration for payment processing platform.",
        bullet_new: "Led AWS migration for payment processing platform, reducing cutover time by 35%.",
      },
      {
        section: "experience",
        description: "Acme fix",
        company: "Acme Corp",
        bullet_old: "Built APIs for payments.",
        bullet_new: "Built APIs for payments, processing 2M transactions daily.",
      },
    ],
    issues,
  );
  assert.equal(hydrated[0]!.company, "Northwind Payments");
  assert.deepEqual(hydrated[0]!.anchor, issues[1]!.anchor);
  assert.equal(hydrated[1]!.company, "Acme Corp");
  assert.deepEqual(hydrated[1]!.anchor, issues[0]!.anchor);
});

test("buildBatchChatMessage includes exact bullet text", () => {
  const message = buildBatchChatMessage([anchoredIssue], tailored);
  assert.match(message, /EXACT current bullet/);
  assert.match(message, /Flint — Meeting Co-Pilot/);
  assert.match(message, /Local-first AI desktop co-pilot/);
});
