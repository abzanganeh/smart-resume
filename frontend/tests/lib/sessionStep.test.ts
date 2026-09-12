import assert from "node:assert/strict"
import test from "node:test"

import { defaultSessionStep, sessionHref } from "@/lib/sessionStep"

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
