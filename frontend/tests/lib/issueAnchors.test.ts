import { summarizeEntryIssueBadges, entryAnchorKey } from "../../lib/issueAnchors";
import type { BlockingIssue } from "../../lib/api";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

const anchoredIssue: BlockingIssue = {
  category: "metric",
  description: "Quantified bullets",
  suggestion: "Add a metric",
  impact: "high",
  fix_effort: "user_input",
  anchor: { section: "experience", entry_index: 0, bullet_index: 1 },
};

console.log("\nissueAnchors tests\n");
const summary = summarizeEntryIssueBadges([anchoredIssue]);
assert(summary[entryAnchorKey("experience", 0)]?.count === 1, "groups issues by entry anchor");
assert(summary[entryAnchorKey("experience", 0)]?.severity === "critical", "maps high impact to critical");
