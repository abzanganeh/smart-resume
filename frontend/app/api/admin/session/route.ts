/**
 * Next.js API route for admin session management.
 *
 * GET  /api/admin/session  → return parsed session or 401
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

export async function GET(req: NextRequest) {
  const raw = req.cookies.get(COOKIE_NAME)?.value
  if (!raw) return NextResponse.json({ error: "no session" }, { status: 401 })

  const session = await decodeSignedAdminSession(raw)
  if (!session) {
    return NextResponse.json({ error: "invalid session" }, { status: 401 })
  }
  if (Date.now() > session.expires_at) {
    return NextResponse.json({ error: "expired" }, { status: 401 })
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
  res.cookies.set(COOKIE_NAME, encoded, {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: ONE_HOUR,
    path: "/",
  })
  return res
}

export async function DELETE() {
  const res = NextResponse.json({ ok: true })
  res.cookies.set(COOKIE_NAME, "", {
    httpOnly: true,
    secure: process.env.NODE_ENV === "production",
    sameSite: "lax",
    maxAge: 0,
    path: "/",
  })
  return res
}
