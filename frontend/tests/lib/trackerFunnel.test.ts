import { describe, it } from "node:test"
import assert from "node:assert/strict"

import type { ApplicationSummary } from "@/lib/tracker"
import { countApplicationsByStatus } from "@/lib/tracker"

const app = (
  status: ApplicationSummary["status"],
  id = "a",
): ApplicationSummary => ({
  id,
  resume_record_id: null,
  jd_title: "Engineer",
  jd_company: "Acme",
  status,
  applied_date: null,
  follow_up_date: null,
  archived_at: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
})

describe("countApplicationsByStatus", () => {
  it("counts apps in each pipeline column", () => {
    const counts = countApplicationsByStatus([
      app("draft", "1"),
      app("applied", "2"),
      app("applied", "3"),
      app("interviewing", "4"),
    ])
    assert.equal(counts.draft, 1)
    assert.equal(counts.applied, 2)
    assert.equal(counts.interviewing, 1)
    assert.equal(counts.offer, 0)
  })
})
