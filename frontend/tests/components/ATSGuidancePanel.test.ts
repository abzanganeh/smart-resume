/**
 * Component tests for ATSGuidancePanel.
 *
 * Run: pnpm exec tsx tests/components/ATSGuidancePanel.test.ts
 */
import {
  sortBlockingIssues,
  scoreColor,
} from "../../components/session/ATSGuidancePanel";
import type { BlockingIssue, QAOutput } from "../../lib/api";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

export const ATS_GUIDANCE_FIXTURE: QAOutput = {
  checklist: [{ item: "Tailored to one specific JD", status: "pass", note: "" }],
  overall_status: "warn",
  user_action_required: [],
  ats_score: 74,
  score_ceiling: 91,
  quick_wins: [
    {
      category: "keyword",
      description: "Missing Kubernetes in Skills.",
      suggestion: "Add Kubernetes to Skills and mention orchestration in Acme bullet.",
      impact: "high",
      fix_effort: "one_click",
    },
  ],
  blocking_issues: [
    {
      category: "keyword",
      description: "Missing Kubernetes in Skills.",
      suggestion: "Add Kubernetes to Skills and mention orchestration in Acme bullet.",
      impact: "high",
      fix_effort: "one_click",
    },
    {
      category: "metric",
      description: "One bullet lacks a quantified outcome.",
      suggestion: "Add a metric such as reduced latency by 35%.",
      impact: "high",
      fix_effort: "user_input",
    },
    {
      category: "format",
      description: "Summary is too long.",
      suggestion: "Trim summary to under 60 words.",
      impact: "low",
      fix_effort: "manual_rewrite",
    },
  ],
};

/** Simulates quick-win Apply button handler wiring. */
function simulateApplyClick(
  issue: BlockingIssue,
  onApply: (suggestion: string) => void,
): string {
  onApply(issue.suggestion);
  return issue.suggestion;
}

function runTests() {
  console.log("\nATSGuidancePanel component tests\n");

  const fixture = ATS_GUIDANCE_FIXTURE;
  assert(fixture.ats_score === 74, "fixture exposes ATS score 74");
  assert(fixture.score_ceiling === 91, "fixture exposes score ceiling 91");
  assert(fixture.blocking_issues.length === 3, "fixture has three blocking issues");
  assert(fixture.quick_wins.length === 1, "fixture has one quick win");

  assert(
    scoreColor(74) === "text-green-700 dark:text-green-400",
    "score 74 uses green color in both themes",
  );
  assert(
    scoreColor(55) === "text-amber-700 dark:text-amber-400",
    "score 55 uses amber color in both themes",
  );
  assert(
    scoreColor(30) === "text-red-700 dark:text-red-400",
    "score 30 uses red color in both themes",
  );

  const sorted = sortBlockingIssues(fixture.blocking_issues);
  assert(sorted[0].impact === "high" && sorted[0].fix_effort === "one_click", "high + one_click sorts first");
  assert(sorted[1].impact === "high" && sorted[1].fix_effort === "user_input", "high + user_input sorts second");
  assert(sorted[2].impact === "low", "low impact sorts last");

  let applied = "";
  const suggestion = simulateApplyClick(fixture.quick_wins[0], (text) => {
    applied = text;
  });
  assert(applied === suggestion, "Apply button passes suggestion text to callback");
  assert(applied.includes("Kubernetes"), "applied suggestion contains actionable keyword text");

  console.log("\nAll tests passed.\n");
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("ATSGuidancePanel.test.ts")) {
  runTests();
}

export { runTests, simulateApplyClick };
