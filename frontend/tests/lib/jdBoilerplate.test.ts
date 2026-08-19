import assert from "node:assert/strict";
import test from "node:test";
import { stripJdBoilerplate } from "@/lib/jdBoilerplate";

test("stripJdBoilerplate removes trailing EEO block after real JD body", () => {
  const body = "Requirements:\n".padEnd(900, "x");
  const input = `${body}\nEqual Opportunity Employer\nWe are an equal opportunity employer.`;
  const out = stripJdBoilerplate(input);
  assert.ok(!out.includes("Equal Opportunity Employer"));
  assert.ok(out.startsWith("Requirements:"));
});

test("stripJdBoilerplate leaves short postings unchanged", () => {
  const input = "Short JD\nEqual Opportunity Employer";
  assert.equal(stripJdBoilerplate(input), input);
});
