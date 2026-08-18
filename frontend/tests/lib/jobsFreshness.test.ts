import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { isJobNew, type JobResult } from "@/lib/jobs"

const baseJob: JobResult = {
  id: "job-1",
  title: "Engineer",
  company: "Acme",
  location: "Remote",
  remote: true,
  salary_min_usd: null,
  salary_max_usd: null,
  employment_type: "",
  posted_date: "2026-08-18T12:00:00Z",
  description: "",
  apply_url: "",
  sources: ["corpus"],
  score: null,
}

describe("isJobNew", () => {
  it("returns true for first_seen_at within 48 hours", () => {
    const now = Date.parse("2026-08-18T20:00:00Z")
    assert.equal(
      isJobNew({ ...baseJob, first_seen_at: "2026-08-18T12:00:00Z" }, now),
      true,
    )
  })

  it("returns false when first_seen_at is missing or stale", () => {
    const now = Date.parse("2026-08-20T12:00:00Z")
    assert.equal(isJobNew({ ...baseJob, first_seen_at: null }, now), false)
    assert.equal(
      isJobNew({ ...baseJob, first_seen_at: "2026-08-15T12:00:00Z" }, now),
      false,
    )
  })
})
