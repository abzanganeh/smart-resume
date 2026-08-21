/**
 * Typed fetch wrappers for all backend auth endpoints.
 *
 * All helpers accept an optional `accessToken` so they can be called from
 * both server (pass token from getAccessToken()) and client (pass token from
 * useSession()) contexts.
 *
 * Endpoints that use httpOnly cookies (refresh, logout) omit the token and
 * rely on the browser sending sr_refresh automatically.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function authHeaders(token?: string): HeadersInit {
  const h: HeadersInit = { "Content-Type": "application/json" }
  if (token) h["Authorization"] = `Bearer ${token}`
  return h
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.detail?.code ?? body?.detail ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

// ── Types ─────────────────────────────────────────────────────────────────────

export interface BackendUser {
  id: string
  email: string
  display_name: string
  tier: string
  credit_balance: number
  auth_provider: string
  email_verified_at: string | null
  has_totp: boolean
  closure_requested_at: string | null
  suspended_at: string | null
  onboarding_completed_at: string | null
  onboarding_ai_choice: "platform" | null
}

export interface AuthSuccess {
  access_token: string
  token_type: "bearer"
  expires_in: number
  user: BackendUser
}

export interface TfaRequired {
  code: "2fa_required"
  challenge_token: string
  expires_in: number
}

export interface EnrollTfaResponse {
  secret: string
  provisioning_uri: string
}

// ── Registration ──────────────────────────────────────────────────────────────

export interface RegisterPayload {
  email: string
  password: string
  display_name?: string
  accepted_tos_version: string
  marketing_opt_in?: boolean
}

export async function registerUser(payload: RegisterPayload): Promise<AuthSuccess> {
  const res = await fetch(`${BASE}/api/auth/register`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    const err = await parseError(res)
    throw new Error(err)
  }
  return res.json()
}

// ── Login ─────────────────────────────────────────────────────────────────────

export interface LoginPayload {
  email: string
  password: string
}

export async function loginUser(
  payload: LoginPayload,
): Promise<AuthSuccess | TfaRequired> {
  const res = await fetch(`${BASE}/api/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  const data = await res.json()
  if (!res.ok) {
    if (data?.detail?.code === "2fa_required") {
      return data.detail as TfaRequired
    }
    throw new Error(data?.detail?.code ?? data?.detail ?? `HTTP ${res.status}`)
  }
  return data as AuthSuccess
}

// ── Me ────────────────────────────────────────────────────────────────────────

export async function fetchMe(accessToken: string): Promise<BackendUser> {
  const res = await fetch(`${BASE}/api/auth/me`, {
    headers: authHeaders(accessToken),
    credentials: "include",
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export interface OnboardingPatchPayload {
  ai_choice?: "platform"
  complete?: boolean
}

export async function patchOnboarding(
  accessToken: string,
  payload: OnboardingPatchPayload,
): Promise<BackendUser> {
  const res = await fetch(`${BASE}/api/auth/onboarding`, {
    method: "PATCH",
    credentials: "include",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

// ── Logout ────────────────────────────────────────────────────────────────────

export async function logoutUser(accessToken: string): Promise<void> {
  await fetch(`${BASE}/api/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders(accessToken),
  })
}

// ── Token refresh ─────────────────────────────────────────────────────────────

export async function refreshSession(): Promise<AuthSuccess> {
  const res = await fetch(`${BASE}/api/auth/refresh`, {
    method: "POST",
    credentials: "include",
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

// ── 2FA ───────────────────────────────────────────────────────────────────────

export async function verify2fa(payload: {
  code?: string
  recovery_code?: string
  challenge_token: string
}): Promise<AuthSuccess> {
  const res = await fetch(`${BASE}/api/auth/2fa/verify`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function enroll2fa(accessToken: string): Promise<EnrollTfaResponse> {
  const res = await fetch(`${BASE}/api/auth/2fa/enroll`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders(accessToken),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function disable2fa(
  accessToken: string,
  payload: { code?: string; recovery_code?: string },
): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/2fa/disable`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders(accessToken),
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

// ── Email verification ────────────────────────────────────────────────────────

export async function sendVerificationEmail(accessToken: string): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/verify/send`, {
    method: "POST",
    credentials: "include",
    headers: authHeaders(accessToken),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

// ── Password reset ────────────────────────────────────────────────────────────

export async function forgotPassword(
  email: string,
): Promise<{ ok: boolean; debug_reset_url?: string }> {
  const res = await fetch(`${BASE}/api/auth/password/forgot`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function resetPassword(payload: {
  token: string
  new_password: string
}): Promise<{ ok: boolean }> {
  const res = await fetch(`${BASE}/api/auth/password/reset`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}
