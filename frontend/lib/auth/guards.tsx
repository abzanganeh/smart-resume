"use client"

/**
 * Client-side auth guards.
 *
 * `useRequireAuth()` — a hook that redirects to /auth if the session is
 *   absent.  Use it at the top of any page component that requires login.
 *
 * `withAuth()` — an HOC that wraps a client component with the same guard.
 *   Prefer `useRequireAuth()` directly; the HOC is here for convenience.
 */
import { useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useEffect, ComponentType } from "react"

/**
 * Redirects to /auth (with callbackUrl) when the user is not signed in.
 * Returns `{ session, status }` so callers can render loading/authenticated
 * states themselves.
 */
export function useRequireAuth(callbackUrl?: string) {
  const { data: session, status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === "loading") return
    if (!session) {
      const dest = callbackUrl ?? (typeof window !== "undefined" ? window.location.pathname : "/")
      router.replace(`/auth?callbackUrl=${encodeURIComponent(dest)}`)
    }
  }, [session, status, router, callbackUrl])

  return { session, status }
}

/**
 * Higher-order component that guards a client component behind auth.
 * Redirects unauthenticated users to /auth.
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
