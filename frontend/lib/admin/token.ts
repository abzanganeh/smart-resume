/**
 * Signed admin session token helpers.
 *
 * The admin session cookie stores a signed payload to prevent client-side
 * tampering and route-guard bypasses. The format is:
 *   base64url(payload).base64url(hmac_sha256(payload))
 */

import type { AdminSessionInfo } from "./types"

export interface SignedAdminSessionPayload {
  access_token: string
  admin: AdminSessionInfo
  expires_at: number
}

const DEFAULT_DEV_SECRET = "local-dev-admin-session-secret-change-me"

function getSecret(): string {
  return (
    process.env.ADMIN_SESSION_SECRET ??
    process.env.NEXTAUTH_SECRET ??
    (process.env.NODE_ENV !== "production" ? DEFAULT_DEV_SECRET : "")
  )
}

function bytesToBase64Url(bytes: Uint8Array): string {
  let binary = ""
  bytes.forEach((b) => {
    binary += String.fromCharCode(b)
  })
  return btoa(binary).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/g, "")
}

function base64UrlToBytes(input: string): Uint8Array {
  const base64 = input.replace(/-/g, "+").replace(/_/g, "/")
  const padded = base64 + "=".repeat((4 - (base64.length % 4)) % 4)
  const binary = atob(padded)
  const bytes = new Uint8Array(binary.length)
  for (let i = 0; i < binary.length; i += 1) {
    bytes[i] = binary.charCodeAt(i)
  }
  return bytes
}

async function signData(data: string, secret: string): Promise<string> {
  const key = await crypto.subtle.importKey(
    "raw",
    new TextEncoder().encode(secret),
    { name: "HMAC", hash: "SHA-256" },
    false,
    ["sign"],
  )
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(data))
  return bytesToBase64Url(new Uint8Array(sig))
}

export async function encodeSignedAdminSession(
  payload: SignedAdminSessionPayload,
): Promise<string> {
  const secret = getSecret()
  if (!secret) throw new Error("ADMIN_SESSION_SECRET is required in production")

  const payloadJson = JSON.stringify(payload)
  const payloadEncoded = bytesToBase64Url(new TextEncoder().encode(payloadJson))
  const signature = await signData(payloadEncoded, secret)
  return `${payloadEncoded}.${signature}`
}

export async function decodeSignedAdminSession(
  token: string,
): Promise<SignedAdminSessionPayload | null> {
  const secret = getSecret()
  if (!secret) return null

  const [payloadEncoded, signature] = token.split(".")
  if (!payloadEncoded || !signature) return null

  const expectedSignature = await signData(payloadEncoded, secret)
  if (signature !== expectedSignature) return null

  try {
    const payloadJson = new TextDecoder().decode(base64UrlToBytes(payloadEncoded))
    return JSON.parse(payloadJson) as SignedAdminSessionPayload
  } catch {
    return null
  }
}
