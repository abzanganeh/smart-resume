import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { computeStepStates } from "@/components/dashboard/stepStack.helpers"

describe("computeStepStates", () => {
  const zeroApps = { active: 0, interviewing: 0, offer: 0, total: 0 }

  it("brand-new user: only master is active, rest locked", () => {
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: false,
      jobRolesStale: false,
      hasJd: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "active")
    assert.equal(s.roles, "locked")
    assert.equal(s.search, "locked")
    assert.equal(s.capture, "locked")
    assert.equal(s.tailor, "locked")
    assert.equal(s.apply, "locked")
    assert.equal(s.applications, "locked")
  })

  it("master resume built: roles unlock; search/capture/tracker still gated on roles", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: false,
      jobRolesStale: false,
      hasJd: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "ready")
    assert.equal(s.roles, "active")
    assert.equal(s.search, "locked")
    assert.equal(s.capture, "locked")
    assert.equal(s.tailor, "locked")
    assert.equal(s.applications, "locked")
  })

  it("roles confirmed: search, capture, and tracker unlock; tailor waits for JD", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.roles, "ready")
    assert.equal(s.search, "ready")
    assert.equal(s.capture, "active")
    assert.equal(s.tailor, "locked")
    assert.equal(s.applications, "active")
  })

  it("first JD captured: tailor unlocks as active", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.capture, "ready")
    assert.equal(s.tailor, "active")
    assert.equal(s.apply, "locked")
  })

  it("stale roles: roles becomes ready-stale, search stays ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: true,
      hasJd: false,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.roles, "ready-stale")
    assert.equal(s.search, "ready")
  })

  it("first tailored resume: tailor ready; apply unlocks as active", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
      tailoredResumeCount: 1,
      applicationCounts: zeroApps,
    })
    assert.equal(s.tailor, "ready")
    assert.equal(s.apply, "active")
  })

  it("first application logged: apply and tracker become ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
      tailoredResumeCount: 3,
      applicationCounts: { active: 1, interviewing: 0, offer: 0, total: 1 },
    })
    assert.equal(s.apply, "ready")
    assert.equal(s.applications, "ready")
  })

  it("offer-stage counts toward hasApplications", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
      tailoredResumeCount: 5,
      applicationCounts: { active: 0, interviewing: 0, offer: 1, total: 1 },
    })
    assert.equal(s.applications, "ready")
    assert.equal(s.apply, "ready")
  })

  it("only rejected / withdrawn applications still count tracker as ready", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
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
      hasJd: true,
      tailoredResumeCount: 5,
      applicationCounts: null,
    })
    assert.equal(s.applications, "active")
  })

  it("contradictory input: jobRolesReady without master resume keeps chain locked", () => {
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: true,
      tailoredResumeCount: 0,
      applicationCounts: zeroApps,
    })
    assert.equal(s.master, "active")
    assert.equal(s.roles, "locked")
    assert.equal(s.search, "locked")
    assert.equal(s.tailor, "locked")
  })

  it("tailored resume count without JD still gates tailor until hasJd is true", () => {
    const s = computeStepStates({
      hasMasterResume: true,
      jobRolesReady: true,
      jobRolesStale: false,
      hasJd: false,
      tailoredResumeCount: 3,
      applicationCounts: zeroApps,
    })
    assert.equal(s.tailor, "locked")
  })

  it("contradictory input: tailored resume count without master resume gates tailor and apply", () => {
    const s = computeStepStates({
      hasMasterResume: false,
      jobRolesReady: false,
      jobRolesStale: false,
      hasJd: false,
      tailoredResumeCount: 3,
      applicationCounts: zeroApps,
    })
    assert.equal(s.tailor, "locked")
    assert.equal(s.apply, "locked")
  })
})
