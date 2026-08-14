import type { BackendUser } from "@/auth"
import {
  buildSessionNewUrl,
  getExtensionHandoff,
} from "@/lib/extensionHandoff"

/** Paths reachable while onboarding is incomplete (AI choice not finished). */
export const ONBOARDING_EXEMPT_PREFIXES = ["/onboarding", "/profile", "/session/new"]

export const ONBOARDING_STEP_COUNT = 4

export function isOnboardingExempt(pathname: string): boolean {
  return ONBOARDING_EXEMPT_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(`${prefix}/`),
  )
}

export function needsOnboarding(user?: BackendUser | null): boolean {
  return Boolean(user && !user.onboarding_completed_at)
}

/** True when an authenticated session should finish onboarding before app routes. */
export function mustCompleteOnboarding(
  session?: { backendUser?: BackendUser | null } | null,
): boolean {
  if (!session) return false
  if (!session.backendUser) return true
  return needsOnboarding(session.backendUser)
}

/** Landing route after sign-in when the user should not stay on /auth. */
export function postAuthLandingPath(
  session?: { backendUser?: BackendUser | null } | null,
): "/onboarding" | "/dashboard" {
  return mustCompleteOnboarding(session) ? "/onboarding" : "/dashboard"
}

export function postOnboardingDestination(_user?: BackendUser | null): string {
  if (typeof window !== "undefined") {
    const stored = sessionStorage.getItem("sr_auth_return_url")
    if (stored && !stored.startsWith("/auth") && stored !== "/onboarding") {
      sessionStorage.removeItem("sr_auth_return_url")
      return stored
    }
    const handoff = getExtensionHandoff()
    if (handoff) return buildSessionNewUrl(handoff)
  }
  return "/dashboard"
}

/** Parse `?step=4` (1-based) into a 0-based step index, or null if invalid. */
export function parseOnboardingStepParam(raw: string | null): number | null {
  if (!raw) return null
  const n = Number(raw)
  if (!Number.isInteger(n) || n < 1 || n > ONBOARDING_STEP_COUNT) return null
  return n - 1
}

/**
 * Pick the onboarding wizard step from server user state.
 * URL step is honored only when prerequisites are met (no skipping ahead).
 */
export function resolveOnboardingStepIndex(
  user: BackendUser | null | undefined,
  options?: { urlStepIndex?: number | null; hasMasterResume?: boolean },
): number {
  if (!user || user.onboarding_completed_at) return -1

  const url = options?.urlStepIndex
  const hasMaster = Boolean(options?.hasMasterResume)
  const hasAiChoice = user.onboarding_ai_choice === "platform"

  if (url != null && url >= 0 && url < ONBOARDING_STEP_COUNT) {
    if (url >= 3 && hasAiChoice && hasMaster) return 3
    if (url >= 2 && hasAiChoice) return 2
    if (url === 1) return 1
    if (url === 0) return 0
  }

  if (hasMaster && hasAiChoice) return 3
  if (hasAiChoice) return 2
  return 0
}
