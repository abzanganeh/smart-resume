import assert from "node:assert/strict"
import test from "node:test"

import { applyResumePatch } from "@/lib/applyResumePatch"
import type { TailoredResumeOutput } from "@/lib/api"
import { isPatchPlaceable } from "@/lib/suggestionHighlight"

const tailored: TailoredResumeOutput = {
  contact: { name: "Ali" },
  summary: "Security engineer.",
  skills: ["Tools: SIEM, Splunk"],
  experience: [
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

test("orphan experience patch with invented company is not placeable", () => {
  const patch = {
    section: "experience" as const,
    company: "Asar",
    add_bullet: "Deployed SIEM correlation rules.",
  }
  assert.equal(isPatchPlaceable(patch, tailored), false)
})

test("retargeted orphan patch applies to real employer", () => {
  const patch = {
    section: "experience" as const,
    company: "IdMe24",
    add_bullet: "Deployed SIEM correlation rules.",
  }
  assert.equal(isPatchPlaceable(patch, tailored), true)
  const result = applyResumePatch(tailored, patch)
  assert.equal(result.applied, true)
  assert.match(result.updated.experience[0]!.bullets.join(" "), /SIEM correlation rules/i)
})
