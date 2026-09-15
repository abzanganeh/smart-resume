import assert from "node:assert/strict"
import test from "node:test"

import { dashboardSessionStep, defaultSessionStep, sessionHref } from "@/lib/sessionStep"

test("defaultSessionStep opens rewrite when phase 3 output exists", () => {
  const step = defaultSessionStep({
    phases: {
      "1": { status: "done", output: {} },
      "2": { status: "done", output: {} },
      "3": { status: "error", output: { summary: "Tailored" } },
    },
  })
  assert.equal(step, "rewrite")
})

test("defaultSessionStep stays on analysis before rewrite", () => {
  const step = defaultSessionStep({
    phases: {
      "1": { status: "done", output: {} },
      "2": { status: "done", output: {} },
    },
  })
  assert.equal(step, "analysis")
})

test("sessionHref adds rewrite step query", () => {
  assert.equal(sessionHref("abc"), "/session/abc")
  assert.equal(sessionHref("abc", "rewrite"), "/session/abc?step=rewrite")
})

test("dashboardSessionStep opens analysis for in-progress drafts", () => {
  assert.equal(
    dashboardSessionStep({ tailoring_stage: "in_progress", current_ats_score: null }),
    "analysis",
  )
})

test("dashboardSessionStep opens rewrite for polished resumes", () => {
  assert.equal(
    dashboardSessionStep({ tailoring_stage: "polished", current_ats_score: 82 }),
    "rewrite",
  )
})
