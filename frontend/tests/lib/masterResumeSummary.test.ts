import assert from "node:assert/strict"
import test from "node:test"

import { summarizeMasterResume } from "@/lib/masterResumeSummary"

test("summarizeMasterResume counts roles, schools, and projects", () => {
  const summary = summarizeMasterResume({
    experience: [{ title: "Eng", company: "A" }, { title: "Lead", company: "B" }],
    education: [{ degree: "BS", institution: "State" }],
    project: [{ name: "P1" }, { name: "P2" }, { name: "P3" }],
  })
  assert.equal(summary, "2 roles · 1 school · 3 projects")
})

test("summarizeMasterResume caps detail at three parts", () => {
  const summary = summarizeMasterResume({
    experience: [{}, {}, {}],
    education: [{}],
    project: [{}],
    cert: ["AWS", "GCP"],
  })
  assert.equal(summary, "3 roles · 1 school · 1 project")
})

test("summarizeMasterResume falls back to section count", () => {
  const summary = summarizeMasterResume({
    summary: "Staff engineer with platform focus.",
    skills: ["Python", "Go"],
    award: ["Pat on back"],
  })
  assert.equal(summary, "3 sections")
})

test("summarizeMasterResume returns null when empty", () => {
  assert.equal(summarizeMasterResume({}), null)
  assert.equal(summarizeMasterResume(null), null)
})
