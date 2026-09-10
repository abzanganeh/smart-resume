import assert from "node:assert/strict"
import test from "node:test"

import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api"
import {
  applyKeywordToSkills,
  canApplyMechanicalQuickWin,
  extractMissingKeyword,
  extractReinforceKeyword,
  tryApplyMechanicalQuickWin,
} from "@/lib/mechanicalFix"

const tailored: TailoredResumeOutput = {
  contact: { name: "Ali" },
  summary: "Software engineer with technical evaluations background.",
  skills: ["Programming Languages: Python, TypeScript", "Cloud Infrastructure: AWS, Docker"],
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
}

test("extractMissingKeyword parses skills suggestion", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Missing",
    suggestion:
      "Add 'cloud infrastructure' to the Skills section AND reinforce it in an Experience bullet.",
    impact: "high",
    fix_effort: "one_click",
  }
  assert.equal(extractMissingKeyword(issue), "cloud infrastructure")
})

test("extractReinforceKeyword parses density suggestion", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "'SIEM' appears only in skills",
    suggestion:
      "Reinforce 'SIEM' in your experience or summary so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  assert.deepEqual(extractReinforceKeyword(issue), {
    keyword: "SIEM",
    targets: ["experience", "summary"],
  })
})

test("applyKeywordToSkills appends to matching category line", () => {
  const updated = applyKeywordToSkills(tailored, "cloud infrastructure")
  assert.ok(updated)
  assert.match(updated.skills[1]!, /cloud infrastructure/i)
})

test("tryApplyMechanicalQuickWin reinforces keyword in experience", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "'technical evaluations' appears only in summary",
    suggestion:
      "Reinforce 'technical evaluations' in your experience so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  const updated = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(updated)
  assert.match(updated.experience[0]!.bullets[0]!, /technical evaluations/i)
})

test("canApplyMechanicalQuickWin is false when no mutation is possible", () => {
  const issue: BlockingIssue = {
    category: "metric",
    description: "Needs a number",
    suggestion: "Add a metric.",
    impact: "high",
    fix_effort: "user_input",
  }
  assert.equal(canApplyMechanicalQuickWin(tailored, issue), false)
})
