"use client"

import { useEffect, useRef } from "react"
import { signOut, useSession } from "next-auth/react"
import { fetchMe } from "@/lib/auth/api"
import { isStaleAuthError } from "@/lib/auth/staleSession"

/**
 * Validates the embedded backend JWT once per token. When the user row is
 * gone (e.g. after a local DB reset) but NextAuth still holds a cookie,
 * signs out so /auth is usable again.
 */
export function StaleSessionGuard() {
  const { data: session, status } = useSession()
  const checkedTokenRef = useRef<string | null>(null)

  useEffect(() => {
    if (status !== "authenticated") {
      checkedTokenRef.current = null
      return
    }

    const token = session?.backendAccessToken
    if (!token || checkedTokenRef.current === token) return
    checkedTokenRef.current = token

    void fetchMe(token).catch((err: unknown) => {
      const message = err instanceof Error ? err.message : ""
      if (isStaleAuthError(message)) {
        void signOut({ callbackUrl: "/auth" })
      }
    })
  }, [status, session?.backendAccessToken])

  return null
}
