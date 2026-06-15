/**
 * Next.js 16 route guard (proxy.ts — replaces the deprecated middleware.ts).
 *
 * Wraps every request with NextAuth's auth() to expose req.auth.
 * Protected routes redirect unauthenticated visitors to /auth.
 * Authenticated visitors with incomplete onboarding go to /onboarding.
 */
import { auth } from "@/auth"
import { NextResponse } from "next/server"
import { decodeSignedAdminSession } from "@/lib/admin/token"
import {
  isOnboardingExempt,
  mustCompleteOnboarding,
  postAuthLandingPath,
} from "@/lib/auth/onboarding"

// Prefix-match protected routes.
const PROTECTED_PREFIXES = [
  "/session/new",
  "/session/",
  "/profile",
  "/billing",
  "/dashboard",
  "/onboarding",
  "/fit",
  "/cover-letter",
  "/jobs",
]

// Routes where authenticated users should NOT linger (redirect to /dashboard).
const AUTH_ONLY_PATHS = ["/auth"]
const ADMIN_AUTH_PATH = "/admin/auth"
const ADMIN_COOKIE = "sr_admin"

export default auth(async function proxy(req) {
  const { pathname } = req.nextUrl
  const session = req.auth

  // ── Separate admin guard (isolated from user NextAuth session) ────────────
  if (pathname.startsWith("/admin") && !pathname.startsWith(ADMIN_AUTH_PATH)) {
    const cookie = req.cookies.get(ADMIN_COOKIE)?.value
    if (!cookie) {
      return NextResponse.redirect(new URL(ADMIN_AUTH_PATH, req.url))
    }
    const adminSession = await decodeSignedAdminSession(cookie)
    if (!adminSession || Date.now() > adminSession.expires_at) {
      return NextResponse.redirect(new URL(ADMIN_AUTH_PATH, req.url))
    }
  }

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/") || pathname.startsWith(prefix),
  )

  if (isProtected && !session) {
    const url = new URL("/auth", req.url)
    // Preserve query string (e.g. extension handoff ?jd_id=…&source=extension).
    url.searchParams.set("callbackUrl", `${pathname}${req.nextUrl.search}`)
    // Duplicate jd_id at top level — OAuth providers sometimes strip nested
    // query params from callbackUrl during the redirect round-trip.
    const jdId = req.nextUrl.searchParams.get("jd_id")
    if (jdId) {
      url.searchParams.set("jd_id", jdId)
      const source = req.nextUrl.searchParams.get("source")
      if (source) url.searchParams.set("source", source)
      const jdReview = req.nextUrl.searchParams.get("jd_review")
      if (jdReview) url.searchParams.set("jd_review", jdReview)
    }
    return NextResponse.redirect(url)
  }

  if (session && mustCompleteOnboarding(session) && !isOnboardingExempt(pathname)) {
    return NextResponse.redirect(new URL("/onboarding", req.url))
  }

  if (AUTH_ONLY_PATHS.some((p) => pathname === p) && session) {
    return NextResponse.redirect(new URL(postAuthLandingPath(session), req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|gif|webp|ico|woff2?|ttf|otf|eot|css|js)$).*)",
  ],
}
