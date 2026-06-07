"use client"

/**
 * Client-side auth guards.
 */
import { signOut, useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useEffect, ComponentType } from "react"
import { isOnboardingExempt, needsOnboarding } from "@/lib/auth/onboarding"

/**
 * Redirects to /auth when the user is not signed in OR when their backend
 * token has expired. When onboarding is incomplete, redirects to /onboarding
 * except on exempt paths (profile, session wizard).
 */
export function useRequireAuth(callbackUrl?: string) {
  const { data: session, status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === "loading") return

    const dest = callbackUrl ?? (typeof window !== "undefined" ? window.location.pathname : "/")
    const authUrl = `/auth?callbackUrl=${encodeURIComponent(dest)}`

    if (!session) {
      router.replace(authUrl)
      return
    }

    if (session.error === "TokenExpired") {
      signOut({ callbackUrl: authUrl })
      return
    }

    const path = typeof window !== "undefined" ? window.location.pathname : dest
    if (
      session.backendUser &&
      needsOnboarding(session.backendUser) &&
      path &&
      !isOnboardingExempt(path)
    ) {
      router.replace("/onboarding")
    }
  }, [session, status, router, callbackUrl])

  return { session, status }
}

/**
 * Higher-order component that guards a client component behind auth.
 */
export function withAuth<P extends object>(
  Component: ComponentType<P>,
  callbackUrl?: string,
): ComponentType<P> {
  function AuthGuarded(props: P) {
    const { session, status } = useRequireAuth(callbackUrl)
    if (status === "loading" || !session) return null
    return <Component {...props} />
  }
  AuthGuarded.displayName = `withAuth(${Component.displayName ?? Component.name ?? "Component"})`
  return AuthGuarded
}
