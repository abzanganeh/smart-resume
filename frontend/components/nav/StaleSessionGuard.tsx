"use client"

import { useEffect, useRef } from "react"
import { signOut, useSession } from "next-auth/react"
import { fetchMe } from "@/lib/auth/api"
import {
  SESSION_REVOKED_EVENT,
  sessionRevokedAuthUrl,
} from "@/lib/parseApiError"
import { refreshBackendSession } from "@/lib/auth/refreshBackendSession"
import { isStaleAuthError } from "@/lib/auth/staleSession"

const REFRESH_BEFORE_SIGNOUT = new Set([
  "Access token expired",
  "Invalid access token",
])

/**
 * Validates the embedded backend JWT once per token. When the user row is
 * gone (e.g. after a local DB reset) but NextAuth still holds a cookie,
 * signs out so /auth is usable again.
 *
 * Also listens for `session_replaced` from in-flight API calls and signs out
 * immediately instead of leaving stale UI with raw error codes.
 */
export function StaleSessionGuard() {
  const { data: session, status, update } = useSession()
  const checkedTokenRef = useRef<string | null>(null)
  const signingOutRef = useRef(false)

  useEffect(() => {
    const onSessionRevoked = () => {
      if (signingOutRef.current) return
      signingOutRef.current = true
      void signOut({ callbackUrl: sessionRevokedAuthUrl() })
    }
    window.addEventListener(SESSION_REVOKED_EVENT, onSessionRevoked)
    return () => window.removeEventListener(SESSION_REVOKED_EVENT, onSessionRevoked)
  }, [])

  useEffect(() => {
    if (status === "unauthenticated") {
      checkedTokenRef.current = null
      signingOutRef.current = false
      return
    }
    if (status !== "authenticated") return

    // BackendTokenRefresh rotates expired JWTs — don't race it with sign-out.
    if (session?.error === "TokenExpired") return

    const token = session?.backendAccessToken
    if (!token || checkedTokenRef.current === token) return

    void (async () => {
      checkedTokenRef.current = token
      try {
        await fetchMe(token)
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : ""
        if (!isStaleAuthError(message)) return
        if (signingOutRef.current) return

        if (REFRESH_BEFORE_SIGNOUT.has(message)) {
          checkedTokenRef.current = null
          const refreshed = await refreshBackendSession(update)
          if (refreshed) return
        }

        signingOutRef.current = true
        void signOut({ callbackUrl: sessionRevokedAuthUrl() })
      }
    })()
  }, [status, session?.backendAccessToken, session?.error, update])

  return null
}
