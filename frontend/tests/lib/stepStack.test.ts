import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { computeStepStates } from "@/components/dashboard/stepStack.helpers"

describe("computeStepStates", () => {
  const zeroApps = { active: 0, interviewing: 0, offer: 0, total: 0 }

  it("brand-new user: only master is active, rest locked (except prepare)", () => {
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: false,
      jobRolesStale: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "active")
    assert.equal(s.roles, "locked")
    assert.equal(s.search, "locked")
    assert.equal(s.tailor, "locked")
    assert.equal(s.applications, "locked")
    assert.equal(s.prepare, "locked")
  })

  it("master resume built: roles + tailor unlock; search still gated on roles", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: false,
      jobRolesStale: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "ready")
    assert.equal(s.roles, "active")
    assert.equal(s.search, "locked")
    assert.equal(s.tailor, "active")
    assert.equal(s.applications, "locked")
  })

  it("roles confirmed: search unlocks; roles show ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.roles, "ready")
    assert.equal(s.search, "ready")
  })

  it("stale roles: roles becomes ready-stale, search stays ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: true,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.roles, "ready-stale")
    assert.equal(s.search, "ready")
  })

  it("first tailored resume: tailor becomes ready; applications unlocks as active", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 1,
      applicationCounts: zeroApps,
    })
    assert.equal(s.tailor, "ready")
    assert.equal(s.applications, "active")
  })

  it("first application logged: applications becomes ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 3,
      applicationCounts: { active: 1, interviewing: 0, offer: 0, total: 1 },
    })
    assert.equal(s.applications, "ready")
  })

  it("offer-stage counts toward hasApplications", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 5,
      applicationCounts: { active: 0, interviewing: 0, offer: 1, total: 1 },
    })
    assert.equal(s.applications, "ready")
  })

  it("only rejected / withdrawn applications still count as ready", () => {
    // funnel counters are zero but total > 0 because everything the user has
    // tracked is in a terminal state — the step is still done.
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 5,
      applicationCounts: { active: 0, interviewing: 0, offer: 0, total: 4 },
    })
    assert.equal(s.applications, "ready")
  })

  it("null applicationCounts is treated as zero", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 5,
      applicationCounts: null,
    })
    assert.equal(s.applications, "active")
  })

  it("prepare step is always locked in v1", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 100,
      applicationCounts: { active: 10, interviewing: 5, offer: 2, total: 17 },
    })
    assert.equal(s.prepare, "locked")
  })

  it("contradictory input: jobRolesReady without master resume keeps chain locked", () => {
    // A stale write or partial fetch could deliver this shape.  We must not
    // unlock search / tailor just because the roles flag is stray-set.
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: true,
      jobRolesStale: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "active")
    assert.equal(s.roles, "locked")
    assert.equal(s.search, "locked")
    assert.equal(s.tailor, "locked")
    assert.equal(s.applications, "locked")
  })

  it("contradictory input: stale roles with no master resume still stays locked", () => {
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: true,
      jobRolesStale: true,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.roles, "locked")
    assert.equal(s.search, "locked")
  })

  it("contradictory input: tailored resume count without master resume gates tailor", () => {
    // If a caller passes a nonzero count with hasMasterResume=false (data
    // race), we err toward the safe locked state rather than showing a
    // green checkmark on a broken chain.
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: false,
      jobRolesStale: false,
      tailoredResumeCount: 3,
      applicationCounts: zeroApps,
    })
    assert.equal(s.tailor, "locked")
  })
})
