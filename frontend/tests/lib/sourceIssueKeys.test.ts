import assert from "node:assert/strict";
import test from "node:test";

import { sourceIssueKeysForPatches } from "@/lib/anchoredPatch";
import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";
import { issueKey } from "@/lib/issueAnchors";

const tailored: TailoredResumeOutput = {
  contact: { name: "Ali" },
  summary: "Summary",
  skills: [],
  experience: [
    {
      title: "Engineer",
      company: "LedgerFlow",
      dates: "2022 – 2024",
      bullets: ["Led AWS migration for payment processing platform."],
      removed_bullets: [],
      keywords_injected: [],
    },
  ],
  education: [],
  projects: [],
  certifications: [],
  rewrite_notes: [],
  metrics_needed: [],
};

test("sourceIssueKeysForPatches resolves inferred-anchor issues after hydrate", () => {
  const issue: BlockingIssue = {
    category: "bullet",
    description: "Bullet length sweet spot (12-25 words)",
    suggestion:
      "Bullet too short (10 words): Led AWS migration for payment processing platform.",
    impact: "medium",
    fix_effort: "manual_rewrite",
  };
  const keys = sourceIssueKeysForPatches(
    tailored,
    [
      {
        section: "experience",
        description: "Expand bullet",
        company: "LedgerFlow",
        bullet_new: "Led AWS migration for payment processing platform, reducing cutover time by 35%.",
        anchor: { section: "experience", entry_index: 0, bullet_index: 0 },
      },
    ],
    [issue],
  );
  assert.equal(keys[0], issueKey({ ...issue, anchor: { section: "experience", entry_index: 0, bullet_index: 0 } }));
});
