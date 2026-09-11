/** Default tailoring tab when opening /session/[id] without ?step=. */

export type SessionTailoringStep = "analysis" | "rewrite" | "export"

export type SessionPhaseSnapshot = {
  phases?: Record<string, { status: string; output: unknown | null }>
  stale?: Record<string, string | null>
}

export function normalizeSessionStep(raw: string | null): SessionTailoringStep {
  if (raw === "keywords" || raw === "audit") return "analysis"
  if (raw === "rewrite" || raw === "export") return raw
  return "analysis"
}

/** Saved sessions with a completed rewrite should open on Tailored Rewrite, not Analysis. */
export function defaultSessionStep(snapshot: SessionPhaseSnapshot): SessionTailoringStep {
  const phase3 = snapshot.phases?.["3"]
  if (phase3?.status === "done" && phase3.output) return "rewrite"
  return "analysis"
}

export function sessionHref(
  sessionId: string,
  step?: SessionTailoringStep,
): string {
  if (!step || step === "analysis") return `/session/${sessionId}`
  return `/session/${sessionId}?step=${step}`
}
