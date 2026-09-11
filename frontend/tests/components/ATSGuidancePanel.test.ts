/**
 * Component tests for ATSGuidancePanel.
 *
 * Run: pnpm exec tsx tests/components/ATSGuidancePanel.test.ts
 */
import {
  sortBlockingIssues,
  scoreColor,
  truncateHeadlinePreview,
  HEADLINE_PREVIEW_LENGTH,
} from "../../components/session/ATSGuidancePanel";
import {
  formatMechanicalOutcomeReceipt,
  formatMechanicalPreviewLine,
  mechanicalOutcomeFromResult,
  shouldShowEmployerConstraintCopy,
  shouldShowUndoButton,
  shouldShowWillChangeLine,
} from "../../components/session/QuickWinCard";
import type { BlockingIssue, QAOutput, TailoredResumeOutput } from "../../lib/api";
import { previewMechanicalQuickWin, tryApplyMechanicalQuickWin } from "../../lib/mechanicalFix";

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

  const withGuidance: QAOutput = {
    ...fixture,
    guidance: {
      resume_quality_score: 72,
      role_fit_score: 41,
      recoverable_ceiling: 68,
      score_meaning: "Test score meaning copy.",
      tailor_verdict: "worth_it",
      tailor_reason: "Worth tailoring for wording.",
      top_actions: [],
    },
  };
  assert(withGuidance.guidance?.role_fit_score === 41, "guidance exposes role fit score");

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

  const long = `${"Word ".repeat(60)}interview readiness.`;
  assert(long.length > HEADLINE_PREVIEW_LENGTH, "fixture headline exceeds preview length");
  const preview = truncateHeadlinePreview(long, HEADLINE_PREVIEW_LENGTH);
  assert(preview.endsWith("…"), "long headline preview ends with ellipsis");
  assert(preview.length < long.length, "preview is shorter than full headline");
  assert(!preview.includes("interview readiness"), "preview truncates before the tail");

  const tailoredFixture: TailoredResumeOutput = {
    contact: { name: "Ali" },
    summary: "Engineer with platform experience.",
    skills: ["Programming Languages: Python, TypeScript"],
    experience: [
      {
        title: "Engineer",
        company: "Acme",
        dates: "2024 – Present",
        bullets: ["Built platform services."],
        removed_bullets: [],
        keywords_injected: [],
      },
    ],
    projects: [],
    education: [],
    certifications: [],
    rewrite_notes: [],
    metrics_needed: [],
  };

  const skillsQuickWin: BlockingIssue = {
    category: "keyword",
    description: "Missing cloud infrastructure in Skills.",
    suggestion: "Add 'cloud infrastructure' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  };
  const skillsPreview = previewMechanicalQuickWin(tailoredFixture, skillsQuickWin);
  const skillsWillChange = formatMechanicalPreviewLine(skillsPreview);
  assert(skillsWillChange !== null && skillsWillChange.includes("cloud infrastructure"), "skills quick win preview names the keyword");
  assert(shouldShowWillChangeLine(skillsWillChange, false), "will-change line shows when not addressed");
  assert(!shouldShowWillChangeLine(skillsWillChange, true), "will-change line hides when addressed");
  assert(shouldShowEmployerConstraintCopy(false, false), "employer constraint shows when not addressed");
  assert(!shouldShowEmployerConstraintCopy(true, false), "employer constraint hides when addressed");
  assert(!shouldShowEmployerConstraintCopy(false, true), "employer constraint hides when outcome shown");
  assert(formatMechanicalPreviewLine(null) === null, "null preview formats to null");
  assert(
    formatMechanicalPreviewLine({ changes: [], unmet: ["already in skills"] }) === null,
    "empty changes format to null",
  );

  const reinforceQuickWin: BlockingIssue = {
    category: "keyword",
    description: "'SIEM' appears only in skills",
    suggestion:
      "Reinforce 'SIEM' in your experience so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  };
  const reinforcePreview = previewMechanicalQuickWin(tailoredFixture, reinforceQuickWin);
  const reinforceWillChange = formatMechanicalPreviewLine(reinforcePreview);
  assert(reinforceWillChange !== null && reinforceWillChange.includes("SIEM"), "reinforce quick win preview names SIEM");

  const metricIssue: BlockingIssue = {
    category: "metric",
    description: "Needs a number",
    suggestion: "Add a metric.",
    impact: "high",
    fix_effort: "user_input",
  };
  assert(
    formatMechanicalPreviewLine(previewMechanicalQuickWin(tailoredFixture, metricIssue)) === null,
    "non-mechanical issue has no preview line",
  );

  const appliedReceipt = formatMechanicalOutcomeReceipt({
    status: "applied",
    changes: ["Add cloud infrastructure"],
  });
  assert(appliedReceipt.headline === "Applied · Add cloud infrastructure", "applied receipt headline");

  const partialReceipt = formatMechanicalOutcomeReceipt({
    status: "partial",
    changes: ["Include SIEM"],
    unmet: ["already in experience"],
  });
  assert(
    partialReceipt.headline === "Partly applied · Include SIEM",
    "partial receipt headline",
  );
  assert(
    JSON.stringify(partialReceipt.details) === JSON.stringify(["already in experience"]),
    "partial receipt lists unmet",
  );
  assert(appliedReceipt.details === undefined, "applied receipt has no details");

  const failedReceipt = formatMechanicalOutcomeReceipt({
    status: "failed",
    reason: "Couldn't apply automatically — already in skills",
  });
  assert(
    failedReceipt.headline === "Couldn't apply automatically — already in skills",
    "failed receipt headline",
  );
  assert(failedReceipt.details === undefined, "failed receipt has no details");

  assert(shouldShowUndoButton({ status: "applied", changes: ["Add SIEM"] }), "undo for applied");
  assert(shouldShowUndoButton({ status: "partial", changes: ["Add SIEM"], unmet: ["x"] }), "undo for partial");
  assert(!shouldShowUndoButton({ status: "failed", reason: "nope" }), "no undo for failed");
  assert(!shouldShowUndoButton(null), "no undo without outcome");

  const alreadyInSkillsIssue: BlockingIssue = {
    category: "keyword",
    description: "Already present",
    suggestion: "Add 'Python' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  };
  const failedOutcome = mechanicalOutcomeFromResult(
    tryApplyMechanicalQuickWin(tailoredFixture, alreadyInSkillsIssue),
  );
  assert(failedOutcome.status === "failed", "empty changes map to failed outcome");
  assert(
    failedOutcome.status === "failed" &&
      failedOutcome.reason.includes("already in skills"),
    "failed outcome includes unmet reason",
  );

  console.log("\nAll tests passed.\n");
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("ATSGuidancePanel.test.ts")) {
  runTests();
}

export { runTests, simulateApplyClick };
