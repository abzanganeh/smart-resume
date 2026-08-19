/**
 * Pure helpers for {@link DashboardStepStack}.  Extracted so we can
 * unit-test the ready/locked/stale state machine without a DOM renderer.
 */

export type StepState = "locked" | "active" | "ready" | "ready-stale"

export interface StepStackInputs {
  hasMasterResume: boolean
  jobRolesReady: boolean
  jobRolesStale: boolean
  tailoredResumeCount: number
  applicationCounts: {
    active: number
    interviewing: number
    offer: number
    /**
     * Total tracked applications regardless of status.  Used for the
     * "applications ready" gate so users whose only apps are rejected /
     * withdrawn still see step 5 as done.
     */
    total: number
  } | null
}

export interface StepStackStates {
  master: StepState
  roles: StepState
  search: StepState
  tailor: StepState
  applications: StepState
  prepare: StepState
}

export function computeStepStates(inputs: StepStackInputs): StepStackStates {
  const {
    hasMasterResume,
    jobRolesReady,
    jobRolesStale,
    tailoredResumeCount,
    applicationCounts,
  } = inputs

  const hasTailored = tailoredResumeCount > 0
  // Applications step is "done" once the user has tracked anything at all,
  // including terminal states (rejected / withdrawn).  The active/interviewing/
  // offer counts still drive the display copy in the UI.
  const hasApplications = (applicationCounts?.total ?? 0) > 0

  // The prerequisite chain is strictly master -> roles -> search.  Even if a
  // stale write leaves `jobRolesReady=true` without a master resume, we refuse
  // to unlock later steps until the earlier ones are actually satisfied.
  const rolesEffectivelyReady = hasMasterResume && jobRolesReady

  return {
    master: hasMasterResume ? "ready" : "active",
    roles: !hasMasterResume
      ? "locked"
      : rolesEffectivelyReady && jobRolesStale
        ? "ready-stale"
        : rolesEffectivelyReady
          ? "ready"
          : "active",
    search: !rolesEffectivelyReady ? "locked" : "ready",
    tailor: !hasMasterResume ? "locked" : hasTailored ? "ready" : "active",
    applications: !hasTailored
      ? "locked"
      : hasApplications
        ? "ready"
        : "active",
    // Prepare (interviews) is always locked in v1.
    prepare: "locked",
  }
}
