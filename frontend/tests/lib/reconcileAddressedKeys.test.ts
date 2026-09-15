import assert from "node:assert/strict";
import test from "node:test";

import type { BlockingIssue, QAOutput } from "@/lib/api";
import { issueKey } from "@/lib/issueAnchors";
import { reconcileAddressedKeys } from "@/lib/reconcileAddressedKeys";

const resolvedIssue: BlockingIssue = {
  category: "bullet",
  description: "Strong action verbs",
  suggestion: "Open with a stronger verb.",
  impact: "medium",
  fix_effort: "manual_rewrite",
  anchor: { section: "experience", entry_index: 0, bullet_index: 0 },
};

const stillFailingIssue: BlockingIssue = {
  category: "metric",
  description: "Missing metric",
  suggestion: "Add a quantified outcome.",
  impact: "high",
  fix_effort: "user_input",
  anchor: { section: "experience", entry_index: 1, bullet_index: 0 },
};

test("reconcileAddressedKeys drops keys for issues still blocking after re-score", () => {
  const prev = new Set([issueKey(resolvedIssue), issueKey(stillFailingIssue)]);
  const qaOut: QAOutput = {
    checklist: [],
    overall_status: "warn",
    user_action_required: [],
    ats_score: 80,
    score_ceiling: 95,
    blocking_issues: [stillFailingIssue],
  };
  const next = reconcileAddressedKeys(prev, qaOut);
  assert.equal(next.has(issueKey(resolvedIssue)), true);
  assert.equal(next.has(issueKey(stillFailingIssue)), false);
});
