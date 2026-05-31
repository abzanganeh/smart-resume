/**
 * Server-side session helpers.
 *
 * `getAccessToken()` retrieves the backend JWT from the current NextAuth
 * session.  Call it in Route Handlers and Server Components.
 */
import { auth } from "@/auth"
import type { BackendUser } from "@/auth"

/**
 * Returns the backend access token for the current request, or null if
 * the session is missing or the token has expired.
 */
export async function getAccessToken(): Promise<string | null> {
  const session = await auth()
  if (!session?.backendAccessToken) return null
  if (session.error === "TokenExpired") return null
  return session.backendAccessToken
}

/**
 * Returns the full backend user record embedded in the NextAuth session.
 */
export async function getSessionUser(): Promise<BackendUser | null> {
  const session = await auth()
  return session?.backendUser ?? null
}

/**
 * Returns the full NextAuth session (convenience re-export so callers
 * don't need to import from two places).
 */
export { auth as getServerSession } from "@/auth"
