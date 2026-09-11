import assert from "node:assert/strict"
import test from "node:test"

import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api"
import {
  applyKeywordToSkills,
  canApplyMechanicalQuickWin,
  extractMissingKeyword,
  extractReinforceKeyword,
  previewMechanicalQuickWin,
  resolveEmployerTargets,
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
    {
      title: "Security Analyst",
      company: "IdMe24",
      dates: "2022 – 2024",
      bullets: ["Monitored alerts."],
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

test("previewMechanicalQuickWin shows skills-only change for add-to-skills issue", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Missing keyword",
    suggestion:
      "Add 'cloud infrastructure' to the Skills section AND reinforce it in an Experience bullet.",
    impact: "high",
    fix_effort: "one_click",
  }
  const preview = previewMechanicalQuickWin(tailored, issue)
  assert.ok(preview)
  assert.equal(preview.changes.length, 1)
  assert.equal(preview.changes[0]!.section, "Skills")
  assert.match(preview.changes[0]!.label, /cloud infrastructure/i)
  assert.deepEqual(preview.unmet, [])
})

test("tryApplyMechanicalQuickWin add-to-skills only touches skills not experience", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Missing keyword",
    suggestion:
      "Add 'cloud infrastructure' to the Skills section AND reinforce it in an Experience bullet.",
    impact: "high",
    fix_effort: "one_click",
  }
  const result = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(result)
  assert.equal(result.changes.length, 1)
  assert.equal(result.changes[0]!.section, "Skills")
  assert.match(result.resume.skills.join(" "), /cloud infrastructure/i)
  assert.equal(
    result.resume.experience[0]!.bullets[0],
    tailored.experience[0]!.bullets[0],
  )
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
  const result = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(result)
  assert.equal(result.changes.length, 1)
  assert.match(result.resume.experience[0]!.bullets[0]!, /technical evaluations/i)
  assert.equal(result.resume.experience[1]!.bullets[0], "Monitored alerts.")
})

test("preview and apply agree on reinforce experience issue", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "'technical evaluations' appears only in summary",
    suggestion:
      "Reinforce 'technical evaluations' in your experience so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  const preview = previewMechanicalQuickWin(tailored, issue)
  const result = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(preview)
  assert.ok(result)
  assert.deepEqual(preview.changes, result.changes)
  assert.deepEqual(preview.unmet, result.unmet)
})

test("tryApplyMechanicalQuickWin add-to-skills leaves second employer unchanged", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Missing keyword",
    suggestion: "Add 'cloud infrastructure' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  }
  const result = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(result)
  assert.equal(result.resume.experience[1]!.bullets[0], "Monitored alerts.")
})

test("reinforce with dual targets applies summary when experience already has keyword", () => {
  const withSiemInExp: TailoredResumeOutput = {
    ...tailored,
    experience: [
      {
        ...tailored.experience[0]!,
        bullets: ["Built SIEM dashboards."],
      },
      tailored.experience[1]!,
    ],
  }
  const issue: BlockingIssue = {
    category: "keyword",
    description: "'SIEM' appears only in experience",
    suggestion:
      "Reinforce 'SIEM' in your experience or summary so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  const preview = previewMechanicalQuickWin(withSiemInExp, issue)
  const result = tryApplyMechanicalQuickWin(withSiemInExp, issue)
  assert.ok(preview)
  assert.ok(result)
  assert.equal(result.changes.length, 1)
  assert.equal(result.changes[0]!.section, "Summary")
  assert.match(result.resume.summary!, /SIEM/i)
  assert.deepEqual(result.unmet, ["already in experience"])
  assert.deepEqual(preview.changes, result.changes)
  assert.deepEqual(preview.unmet, result.unmet)
})

test("reinforce returns unmet when keyword already in all targets", () => {
  const fullyCovered: TailoredResumeOutput = {
    ...tailored,
    summary: "Software engineer with technical evaluations background.",
    experience: [
      {
        ...tailored.experience[0]!,
        bullets: ["Led technical evaluations for platform services."],
      },
    ],
  }
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Already covered",
    suggestion:
      "Reinforce 'technical evaluations' in your experience or summary so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  const result = tryApplyMechanicalQuickWin(fullyCovered, issue)
  assert.ok(result)
  assert.equal(result.changes.length, 0)
  assert.ok(result.unmet.includes("already in summary"))
  assert.ok(result.unmet.includes("already in experience"))
  assert.equal(result.resume.summary, fullyCovered.summary)
  assert.equal(
    result.resume.experience[0]!.bullets[0],
    fullyCovered.experience[0]!.bullets[0],
  )
})

test("tryApplyMechanicalQuickWin returns unmet when keyword already in skills", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Already present",
    suggestion: "Add 'Python' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  }
  const result = tryApplyMechanicalQuickWin(tailored, issue)
  assert.ok(result)
  assert.equal(result.changes.length, 0)
  assert.deepEqual(result.unmet, ["already in skills"])
  assert.deepEqual(result.resume.skills, tailored.skills)
  assert.deepEqual(result.resume.experience, tailored.experience)
})

test("previewMechanicalQuickWin reports already in skills", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Already present",
    suggestion: "Add 'Python' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  }
  const preview = previewMechanicalQuickWin(tailored, issue)
  assert.ok(preview)
  assert.equal(preview.changes.length, 0)
  assert.deepEqual(preview.unmet, ["already in skills"])
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

test("canApplyMechanicalQuickWin is false when keyword already in skills", () => {
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Already present",
    suggestion: "Add 'Python' to the Skills section.",
    impact: "high",
    fix_effort: "one_click",
  }
  assert.equal(canApplyMechanicalQuickWin(tailored, issue), false)
})

test("resolveEmployerTargets returns experience entries with indices", () => {
  const targets = resolveEmployerTargets(tailored)
  assert.equal(targets.length, 2)
  assert.deepEqual(targets[0], { company: "Acme", title: "Engineer", index: 0 })
  assert.deepEqual(targets[1], {
    company: "IdMe24",
    title: "Security Analyst",
    index: 1,
  })
})

test("resolveEmployerTargets filters blank entries and keeps title-only", () => {
  const sparse: TailoredResumeOutput = {
    ...tailored,
    experience: [
      { title: "", company: "", dates: "", bullets: [], removed_bullets: [], keywords_injected: [] },
      { title: "Consultant", company: "", dates: "2020", bullets: ["Advised."], removed_bullets: [], keywords_injected: [] },
      tailored.experience[0]!,
    ],
  }
  const targets = resolveEmployerTargets(sparse)
  assert.equal(targets.length, 2)
  assert.deepEqual(targets[0], { company: "", title: "Consultant", index: 1 })
  assert.deepEqual(targets[1], { company: "Acme", title: "Engineer", index: 2 })
})

test("reinforce with empty experience bullets returns unmet", () => {
  const noBullets: TailoredResumeOutput = {
    ...tailored,
    experience: [{ ...tailored.experience[0]!, bullets: [] }],
  }
  const issue: BlockingIssue = {
    category: "keyword",
    description: "Needs bullet",
    suggestion:
      "Reinforce 'SIEM' in your experience so it appears in 2+ sections (ATS keyword density rule).",
    impact: "high",
    fix_effort: "one_click",
  }
  const preview = previewMechanicalQuickWin(noBullets, issue)
  const result = tryApplyMechanicalQuickWin(noBullets, issue)
  assert.ok(preview)
  assert.ok(result)
  assert.equal(result.changes.length, 0)
  assert.deepEqual(result.unmet, ["no experience bullet to reinforce"])
  assert.deepEqual(preview.changes, result.changes)
  assert.deepEqual(preview.unmet, result.unmet)
})
