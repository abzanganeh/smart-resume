import type { BackendUser } from "@/auth"

/** Paths reachable while onboarding is incomplete (AI choice not finished). */
export const ONBOARDING_EXEMPT_PREFIXES = ["/onboarding", "/profile", "/session/new"]

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
