/**
 * NextAuth.js v5 configuration.
 *
 * Session strategy: JWT (stored in encrypted httpOnly cookie by NextAuth).
 * The backend's own access token (15-min HS256 JWT) is embedded inside
 * NextAuth's JWT so every server-side caller can forward it to FastAPI.
 * The backend's refresh token rides in a *separate* httpOnly cookie
 * (sr_refresh) set by FastAPI — browsers send it automatically on fetch
 * requests to localhost:8000 with `credentials:"include"`.
 *
 * OAuth SSO (Google / GitHub):
 *   NextAuth handles the OAuth code exchange with the provider.
 *   After obtaining the access_token, we call our backend's
 *   POST /api/auth/callback to create/sync the backend user.
 *   NOTE: The backend currently expects the raw OAuth code, but we only
 *   have the already-exchanged access_token at this point. The backend
 *   will need a small update (see TODO below) to accept access_tokens.
 *   Until then, OAuth sign-in creates a NextAuth session but the
 *   backendAccessToken will be absent; protected API calls will fail with
 *   an appropriate error that guides the user to link via email/password.
 */
import NextAuth from "next-auth"
import type { User } from "next-auth"
import Google from "next-auth/providers/google"
import GitHub from "next-auth/providers/github"
import Credentials from "next-auth/providers/credentials"

const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"
const NEXTAUTH_URL = process.env.NEXTAUTH_URL ?? "http://localhost:3000"
const isLocalEnv =
  process.env.NEXT_PUBLIC_APP_ENV === "local" || process.env.NODE_ENV !== "production"
const nextAuthSecret =
  process.env.NEXTAUTH_SECRET ??
  (isLocalEnv ? "local-dev-nextauth-secret-change-me" : undefined)

// ── Types shared with next-auth.d.ts augmentation ────────────────────────────

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
}

interface BackendAuthUser extends User {
  backendAccessToken?: string
  backendExpiresAt?: number
  backendUser?: BackendUser
}

// ── Backend OAuth sync helper ─────────────────────────────────────────────────

/**
 * Call the backend after an OAuth sign-in to create/sync the backend user.
 *
 * TODO (backend): POST /api/auth/callback currently re-exchanges the code
 * with the provider.  Once the backend can also accept a verified
 * `access_token` or `id_token`, remove the "code exchange" path and pass
 * the token directly.  Until then this call is expected to fail for OAuth
 * sign-ins and we fall through gracefully.
 */
async function syncOAuthWithBackend(
  provider: string,
  accessToken: string | undefined,
  idToken: string | undefined,
  callbackUrl: string,
): Promise<{ access_token: string; expires_in: number; user: BackendUser } | null> {
  const token = idToken ?? accessToken
  if (!token) return null
  try {
    const res = await fetch(`${API_URL}/api/auth/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ provider, code: token, redirect_uri: callbackUrl }),
    })
    if (!res.ok) return null
    return res.json()
  } catch {
    return null
  }
}

// ── NextAuth config ───────────────────────────────────────────────────────────

export const { handlers, signIn, signOut, auth } = NextAuth({
  secret: nextAuthSecret,
  providers: [
    Google({
      clientId: process.env.GOOGLE_CLIENT_ID!,
      clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
    }),
    GitHub({
      clientId: process.env.GITHUB_CLIENT_ID!,
      clientSecret: process.env.GITHUB_CLIENT_SECRET!,
    }),

    /**
     * Primary credentials provider: email + password.
     * Calls POST /api/auth/login on the backend.
     * Throws a structured error string when 2FA is required so the UI
     * can show the TOTP step without a full page redirect.
     */
    Credentials({
      id: "credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) return null

        const res = await fetch(`${API_URL}/api/auth/login`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "include",
          body: JSON.stringify({
            email: credentials.email,
            password: credentials.password,
          }),
        })

        const data = await res.json()

        if (res.status === 401 && data?.detail?.code === "2fa_required") {
          // Signal 2FA to the UI; the challenge_token is decoded by the page.
          throw new Error(
            `2fa_required:${data.detail.challenge_token}:${data.detail.expires_in}`,
          )
        }

        if (!res.ok) return null

        const user = data.user as BackendUser
        return {
          id: user.id,
          email: user.email,
          name: user.display_name,
          image: null,
          backendAccessToken: data.access_token as string,
          backendExpiresAt: Date.now() + (data.expires_in as number) * 1000,
          backendUser: user,
        }
      },
    }),

    /**
     * "Token" credentials provider: accepts a pre-verified backend
     * access_token.  Used after:
     *   - Successful 2FA verification (client calls POST /api/auth/2fa/verify)
     *   - Successful OAuth sync (after SSO callback returns tokens)
     *
     * The caller serialises the backend user as JSON in `user_json`.
     */
    Credentials({
      id: "token",
      credentials: {
        access_token: {},
        expires_in: {},
        user_json: {},
      },
      async authorize(credentials) {
        if (!credentials?.access_token || !credentials?.user_json) return null
        try {
          const user = JSON.parse(credentials.user_json as string) as BackendUser
          return {
            id: user.id,
            email: user.email,
            name: user.display_name,
            image: null,
            backendAccessToken: credentials.access_token as string,
            backendExpiresAt:
              Date.now() + Number(credentials.expires_in ?? 900) * 1000,
            backendUser: user,
          }
        } catch {
          return null
        }
      },
    }),
  ],

  callbacks: {
    async jwt({ token, user, account }) {
      // ── Initial sign-in ────────────────────────────────────────────────────
      if (user && (account?.provider === "credentials" || account?.provider === "token")) {
        const backendUser = user as BackendAuthUser
        token.backendAccessToken = backendUser.backendAccessToken
        token.backendExpiresAt = backendUser.backendExpiresAt
        token.backendUser = backendUser.backendUser
        return token
      }

      // ── OAuth sign-in (Google / GitHub) ───────────────────────────────────
      if (user && account && (account.provider === "google" || account.provider === "github")) {
        const synced = await syncOAuthWithBackend(
          account.provider,
          account.access_token ?? undefined,
          account.id_token ?? undefined,
          `${NEXTAUTH_URL}/api/auth/callback/${account.provider}`,
        )
        if (synced) {
          token.backendAccessToken = synced.access_token
          token.backendExpiresAt = Date.now() + synced.expires_in * 1000
          token.backendUser = synced.user
        } else {
          // OAuth sync with backend not yet available — mark so UI can inform user.
          token.error = "OAuthBackendSyncPending"
        }
        return token
      }

      // ── Subsequent requests: check expiry ─────────────────────────────────
      if (!token.backendExpiresAt || Date.now() < (token.backendExpiresAt as number)) {
        return token
      }

      // Token has expired.  The client detects session.error === "TokenExpired"
      // and calls POST /api/auth/refresh (forwarding the sr_refresh httpOnly
      // cookie) then calls update() to refresh the NextAuth session.
      return { ...token, error: "TokenExpired" }
    },

    async session({ session, token }) {
      return {
        ...session,
        backendAccessToken: token.backendAccessToken as string | undefined,
        backendUser: token.backendUser as BackendUser | undefined,
        error: token.error as string | undefined,
      }
    },
  },

  pages: {
    signIn: "/auth",
    error: "/auth",
  },

  session: { strategy: "jwt" },
})
