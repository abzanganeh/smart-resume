/**
 * Next.js middleware.
 *
 * Admin route protection:
 *   - All /admin/* routes (except /admin/auth) require the `sr_admin`
 *     cookie.  If absent or expired, redirect to /admin/auth.
 *
 * User route protection is handled per-page via useRequireAuth() hooks
 * (not middleware) to keep OAuth redirect logic in one place.
 */

import { NextRequest, NextResponse } from "next/server"

const ADMIN_COOKIE = "sr_admin"
const ADMIN_AUTH_PATH = "/admin/auth"

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl

  // Only handle /admin/* routes
  if (!pathname.startsWith("/admin")) return NextResponse.next()

  // Allow the login page itself through
  if (pathname.startsWith(ADMIN_AUTH_PATH)) return NextResponse.next()

  // Allow API session route through (used by layout to read session)
  if (pathname.startsWith("/api/admin/session")) return NextResponse.next()

  const raw = req.cookies.get(ADMIN_COOKIE)?.value
  if (!raw) {
    return NextResponse.redirect(new URL(ADMIN_AUTH_PATH, req.url))
  }

  try {
    const session = JSON.parse(Buffer.from(raw, "base64").toString("utf-8"))
    if (Date.now() > session.expires_at) {
      return NextResponse.redirect(new URL(ADMIN_AUTH_PATH, req.url))
    }
  } catch {
    return NextResponse.redirect(new URL(ADMIN_AUTH_PATH, req.url))
  }

  return NextResponse.next()
}

export const config = {
  matcher: ["/admin/:path*"],
}
