"use client"

import { useEffect, useRef } from "react"
import { getSession, useSession } from "next-auth/react"
import {
  refreshBackendSession,
  refreshBackendSessionIfNeeded,
} from "@/lib/auth/refreshBackendSession"

// 24 h access tokens: check every 10 min; refresh only in the last hour.
const POLL_MS = 10 * 60 * 1000
const REFRESH_BUFFER_MS = 60 * 60 * 1000

/** Keeps the embedded backend JWT fresh using the sr_refresh cookie. */
export function BackendTokenRefresh() {
  const { data: session, status, update } = useSession()
  const updateRef = useRef(update)
  updateRef.current = update

  const expiredRecoveryRef = useRef(false)

  // One-shot recovery when NextAuth marks the embedded JWT expired.
  useEffect(() => {
    if (status !== "authenticated" || session?.error !== "TokenExpired") {
      expiredRecoveryRef.current = false
      return
    }
    if (expiredRecoveryRef.current) return
    expiredRecoveryRef.current = true
    void refreshBackendSession(updateRef.current)
  }, [status, session?.error])

  // Periodic proactive refresh — deps stable so session.update() does not re-arm loops.
  useEffect(() => {
    if (status !== "authenticated") return

    const id = window.setInterval(() => {
      void (async () => {
        const current = await getSession()
        const expiresAt = (current as { backendExpiresAt?: number } | null)
          ?.backendExpiresAt
        await refreshBackendSessionIfNeeded(
          updateRef.current,
          expiresAt,
          REFRESH_BUFFER_MS,
        )
      })()
    }, POLL_MS)

    return () => window.clearInterval(id)
  }, [status])

  return null
}
