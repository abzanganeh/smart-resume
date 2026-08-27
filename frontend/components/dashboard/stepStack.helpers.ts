/**
 * Pure helpers for {@link DashboardStepStack}.  Extracted so we can
 * unit-test the ready/locked/stale state machine without a DOM renderer.
 */

export type StepState = "locked" | "active" | "ready" | "ready-stale"

export interface StepStackInputs {
  hasMasterResume: boolean
  jobRolesReady: boolean
  jobRolesStale: boolean
  /** Saved job or any tailored resume implies the user has a JD in the system. */
  hasJd: boolean
  tailoredResumeCount: number
  applicationCounts: {
    active: number
    interviewing: number
    offer: number
    /**
     * Total tracked applications regardless of status.  Used for the
     * "applications ready" gate so users whose only apps are rejected /
     * withdrawn still see step 7 as done.
     */
    total: number
  } | null
}

export interface StepStackStates {
  master: StepState
  roles: StepState
  search: StepState
  capture: StepState
  tailor: StepState
  apply: StepState
  applications: StepState
}

export function computeStepStates(inputs: StepStackInputs): StepStackStates {
  const {
    hasMasterResume,
    jobRolesReady,
    jobRolesStale,
    hasJd,
    tailoredResumeCount,
    applicationCounts,
  } = inputs

  const hasTailored = tailoredResumeCount > 0
  const hasApplications = (applicationCounts?.total ?? 0) > 0

  // The prerequisite chain is strictly master -> roles.  Even if a stale write
  // leaves `jobRolesReady=true` without a master resume, we refuse to unlock
  // later steps until the earlier ones are actually satisfied.
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
    capture: !rolesEffectivelyReady ? "locked" : hasJd ? "ready" : "active",
    tailor: !hasMasterResume
      ? "locked"
      : !hasJd
        ? "locked"
        : hasTailored
          ? "ready"
          : "active",
    apply: !hasTailored
      ? "locked"
      : hasApplications
        ? "ready"
        : "active",
    applications: !rolesEffectivelyReady
      ? "locked"
      : hasApplications
        ? "ready"
        : "active",
  }
}
