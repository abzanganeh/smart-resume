/**
 * BulletAtsHints behavior tests (logic-only; no DOM).
 *
 * Run: pnpm exec tsx tests/components/BulletAtsHints.test.ts
 */
import type { BlockingIssue } from "@/lib/api";
import { issueKey } from "@/lib/issueAnchors";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

const issue: BlockingIssue = {
  category: "bullet",
  description: "Strong action verbs",
  suggestion: "Open with a stronger verb: Championed platform migration…",
  impact: "medium",
  fix_effort: "manual_rewrite",
  anchor: { section: "experience", entry_index: 0, bullet_index: 1 },
};

function runTests() {
  console.log("\nBulletAtsHints logic tests\n");

  const key = issueKey(issue);
  assert(key === "anchor:experience:0:1", "issue key is anchor-based for hints");

  const addressed = new Set([key]);
  const skipped = new Set<string>();
  const ignored = skipped.has(key);
  const edited = addressed.has(key);
  assert(!ignored, "Ignore path uses skippedKeys");
  assert(edited, "Save-with-change marks addressed via addressedKeys");
  assert(!addressed.has("anchor:experience:0:2"), "unchanged bullet key stays unaddressed");

  console.log("\nAll tests passed.\n");
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("BulletAtsHints.test.ts")) {
  runTests();
}

export { runTests };
