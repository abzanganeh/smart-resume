/**
 * Admin session management.
 *
 * The admin session is completely separate from the user NextAuth session.
 * On successful admin login + TOTP verification the backend issues a JWT
 * stored in an httpOnly cookie (`sr_admin`).  This module provides
 * client-side helpers to:
 *   - Read the current admin session via the Next.js session API route.
 *   - Store the admin token after login.
 *   - Clear the session on logout.
 *
 * Server-side route protection is handled by middleware.ts.
 */

import type { AdminSession, AdminSessionInfo } from "./types"

const SESSION_ROUTE = "/api/admin/session"

// ── Types ─────────────────────────────────────────────────────────────────────

export interface StoredAdminSession {
  access_token: string
  admin: AdminSessionInfo
  /** UNIX ms */
  expires_at: number
}

// ── Client helpers ────────────────────────────────────────────────────────────

/**
 * Fetch the current admin session from the Next.js API route.
 * Returns null when no session cookie is present.
 */
export async function getAdminSession(): Promise<StoredAdminSession | null> {
  try {
    const res = await fetch(SESSION_ROUTE, { credentials: "include" })
    if (!res.ok) return null
    return res.json() as Promise<StoredAdminSession>
  } catch {
    return null
  }
}

/**
 * Store the admin token after a successful login+TOTP flow.
 */
export async function storeAdminSession(
  access_token: string,
  admin: AdminSessionInfo,
  expires_in: number,
): Promise<void> {
  await fetch(SESSION_ROUTE, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ access_token, admin, expires_in }),
  })
}

/**
 * Clear the admin session (logout).
 */
export async function clearAdminSession(): Promise<void> {
  await fetch(SESSION_ROUTE, { method: "DELETE", credentials: "include" })
}

/**
 * Returns the number of milliseconds until the session expires.
 * Returns 0 if already expired.
 */
export function sessionMsRemaining(session: StoredAdminSession): number {
  return Math.max(0, session.expires_at - Date.now())
}

/**
 * True when session will expire within `warningMs` (default 5 min).
 */
export function sessionExpiringSoon(
  session: StoredAdminSession,
  warningMs = 5 * 60 * 1000,
): boolean {
  return sessionMsRemaining(session) < warningMs
}

export type { AdminSession }
