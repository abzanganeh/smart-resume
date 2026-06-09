import type { BackendUser } from "@/auth"

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

export function postOnboardingDestination(_user?: BackendUser | null): string {
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
  const hasAiChoice = user.onboarding_ai_choice === "platform" || user.onboarding_ai_choice === "byok"

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
