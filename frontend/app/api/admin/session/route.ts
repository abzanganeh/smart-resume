/**
 * Next.js API route for admin session management.
 *
 * GET  /api/admin/session  → return parsed session or JSON null (200)
 * POST /api/admin/session  → set httpOnly cookie after login
 * DELETE /api/admin/session → clear cookie (logout)
 *
 * The `sr_admin` cookie holds a JSON payload with access_token, admin info,
 * and expiry timestamp — encrypted by Next.js response.cookies helper which
 * sets SameSite=Lax, HttpOnly, Secure (in production).
 */

import { NextRequest, NextResponse } from "next/server"
import type { AdminSessionInfo } from "@/lib/admin/types"
import {
  decodeSignedAdminSession,
  encodeSignedAdminSession,
} from "@/lib/admin/token"

const COOKIE_NAME = "sr_admin"
const ONE_HOUR = 3600

/** Only mark cookies Secure when the browser reached us over HTTPS. */
function cookieSecure(req: NextRequest): boolean {
  const forwarded = req.headers.get("x-forwarded-proto")?.split(",")[0]?.trim()
  if (forwarded) return forwarded === "https"
  return req.nextUrl.protocol === "https:"
}

function cookieOptions(req: NextRequest, maxAge: number) {
  return {
    httpOnly: true,
    secure: cookieSecure(req),
    sameSite: "lax" as const,
    maxAge,
    path: "/",
  }
}

export async function GET(req: NextRequest) {
  const raw = req.cookies.get(COOKIE_NAME)?.value
  if (!raw) return NextResponse.json(null)

  const session = await decodeSignedAdminSession(raw)
  if (!session) {
    return NextResponse.json(null)
  }
  if (Date.now() > session.expires_at) {
    return NextResponse.json(null)
  }
  return NextResponse.json(session)
}

export async function POST(req: NextRequest) {
  const body = await req.json() as {
    access_token: string
    admin: AdminSessionInfo
    expires_in: number
  }

  const expires_at = Date.now() + body.expires_in * 1000
  const payload = {
    access_token: body.access_token,
    admin: body.admin,
    expires_at,
  }

  const encoded = await encodeSignedAdminSession(payload)

  const res = NextResponse.json({ ok: true })
  res.cookies.set(COOKIE_NAME, encoded, cookieOptions(req, ONE_HOUR))
  return res
}

export async function DELETE(req: NextRequest) {
  const res = NextResponse.json({ ok: true })
  res.cookies.set(COOKIE_NAME, "", cookieOptions(req, 0))
  return res
}
