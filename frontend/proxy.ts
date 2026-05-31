/**
 * Next.js 16 route guard (proxy.ts — replaces the deprecated middleware.ts).
 *
 * Wraps every request with NextAuth's auth() to expose req.auth.
 * Protected routes redirect unauthenticated visitors to /auth.
 * Authenticated visitors hitting /auth are redirected to /dashboard.
 */
import { auth } from "@/auth"
import { NextResponse } from "next/server"

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

export default auth(function proxy(req) {
  const { pathname } = req.nextUrl
  const session = req.auth

  const isProtected = PROTECTED_PREFIXES.some(
    (prefix) => pathname === prefix || pathname.startsWith(prefix + "/") || pathname.startsWith(prefix),
  )

  if (isProtected && !session) {
    const url = new URL("/auth", req.url)
    url.searchParams.set("callbackUrl", pathname)
    return NextResponse.redirect(url)
  }

  if (AUTH_ONLY_PATHS.some((p) => pathname === p) && session) {
    return NextResponse.redirect(new URL("/dashboard", req.url))
  }

  return NextResponse.next()
})

export const config = {
  matcher: [
    "/((?!api/auth|_next/static|_next/image|favicon\\.ico|.*\\.(?:png|jpg|jpeg|svg|gif|webp|ico|woff2?|ttf|otf|eot|css|js)$).*)",
  ],
}
