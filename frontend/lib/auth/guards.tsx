"use client"

/**
 * Client-side auth guards.
 */
import { signOut, useSession } from "next-auth/react"
import { useRouter } from "next/navigation"
import { useEffect, ComponentType } from "react"

/**
 * Redirects to /auth when the user is not signed in OR when their backend
 * token has expired. Returns `{ session, status }` for the caller to render.
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
