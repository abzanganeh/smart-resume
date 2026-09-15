import {
  buildBulletAtsIssueMap,
  bulletAnchorKey,
  issueKey,
  summarizeEntryIssueBadges,
  entryAnchorKey,
} from "../../lib/issueAnchors";
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

assert(
  issueKey(anchoredIssue) === bulletAnchorKey("experience", 0, 1),
  "issueKey matches bullet anchor key",
);
const bulletMap = buildBulletAtsIssueMap([anchoredIssue]);
assert(
  bulletMap[bulletAnchorKey("experience", 0, 1)]?.length === 1,
  "buildBulletAtsIssueMap groups by bullet anchor",
);
