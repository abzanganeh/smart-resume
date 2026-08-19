/**
 * NextAuth.js v5 configuration.
 *
 * Session strategy: JWT (stored in encrypted httpOnly cookie by NextAuth).
 * The backend's own access token (HS256 JWT) is embedded inside
 * NextAuth's JWT so every server-side caller can forward it to FastAPI.
 * The backend's refresh token rides in a *separate* httpOnly cookie
 * (sr_refresh) set by FastAPI — browsers send it automatically on fetch
 * requests to localhost:8000 with `credentials:"include"`.
 *
 * OAuth SSO (Google / GitHub / Microsoft / LinkedIn / Apple):
 *   NextAuth handles the OAuth code exchange with the provider.
 *   After obtaining tokens, we call POST /api/auth/callback with
 *   id_token or access_token so FastAPI creates/syncs the User row
 *   and returns backend access + refresh tokens embedded in the session.
 */
import NextAuth from "next-auth"
import type { User } from "next-auth"
import Google from "next-auth/providers/google"
import GitHub from "next-auth/providers/github"
import MicrosoftEntraID from "next-auth/providers/microsoft-entra-id"
import LinkedIn from "next-auth/providers/linkedin"
import Credentials from "next-auth/providers/credentials"

const API_URL =
  process.env.INTERNAL_API_URL ??
  process.env.NEXT_PUBLIC_API_URL ??
  "http://localhost:8000"
const isLocalEnv =
  process.env.NEXT_PUBLIC_APP_ENV === "local" || process.env.NODE_ENV !== "production"

// Pinned NEXTAUTH_URL forces OAuth redirect_uri to localhost even when the browser
// uses a LAN IP — PKCE/state cookies then live on 192.168.x.x while the callback
// hits localhost and Auth.js returns Configuration. In local dev, trust Host instead.
if (
  isLocalEnv &&
  process.env.AUTH_TRUST_HOST !== "false" &&
  process.env.AUTH_TRUST_HOST !== "0"
) {
  delete process.env.AUTH_URL
  delete process.env.NEXTAUTH_URL
}

const NEXTAUTH_URL = process.env.NEXTAUTH_URL ?? "http://localhost:3000"
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
  onboarding_completed_at: string | null
  onboarding_ai_choice: "platform" | null
}

interface BackendAuthUser extends User {
  backendAccessToken?: string
  backendExpiresAt?: number
  backendUser?: BackendUser
}

// ── Backend OAuth sync helper ─────────────────────────────────────────────────

type OAuthSyncResult =
  | { ok: true; access_token: string; expires_in: number; user: BackendUser }
  | { ok: false; error: string }

/**
 * Call the backend after an OAuth sign-in to create/sync the backend user.
 * NextAuth has already exchanged the auth code; pass id_token or access_token.
 */
async function syncOAuthWithBackend(
  provider: string,
  accessToken: string | undefined,
  idToken: string | undefined,
  callbackUrl: string,
): Promise<OAuthSyncResult> {
  if (!idToken && !accessToken) return { ok: false, error: "OAuthBackendSyncPending" }
  try {
    const res = await fetch(`${API_URL}/api/auth/callback`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        provider,
        ...(idToken ? { id_token: idToken } : {}),
        ...(accessToken ? { access_token: accessToken } : {}),
        redirect_uri: callbackUrl,
      }),
    })
    if (!res.ok) {
      try {
        const data = (await res.json()) as {
          detail?: { code?: string; with_provider?: string }
        }
        const code = data.detail?.code
        if (code === "email_already_registered" && data.detail?.with_provider) {
          return {
            ok: false,
            error: `email_registered_with_sso:${data.detail.with_provider}`,
          }
        }
        if (code) return { ok: false, error: code }
      } catch {
        /* ignore parse errors */
      }
      return { ok: false, error: "OAuthBackendSyncPending" }
    }
    const body = (await res.json()) as {
      access_token: string
      expires_in: number
      user: BackendUser
    }
    return { ok: true, ...body }
  } catch {
    return { ok: false, error: "OAuthBackendSyncPending" }
  }
}

const PLACEHOLDER_OAUTH_CLIENT_IDS = new Set([
  "local-google-id",
  "local-github-id",
  "local-microsoft-id",
  "local-linkedin-id",
  "playwright-google-client-id",
  "playwright-github-client-id",
])

function oauthCredentialsConfigured(
  clientId: string | undefined,
  clientSecret: string | undefined,
): boolean {
  const id = clientId?.trim() ?? ""
  const secret = clientSecret?.trim() ?? ""
  if (!id || !secret) return false
  return !PLACEHOLDER_OAUTH_CLIENT_IDS.has(id)
}

const googleOAuthConfigured = oauthCredentialsConfigured(
  process.env.GOOGLE_CLIENT_ID,
  process.env.GOOGLE_CLIENT_SECRET,
)
const githubOAuthConfigured = oauthCredentialsConfigured(
  process.env.GITHUB_CLIENT_ID,
  process.env.GITHUB_CLIENT_SECRET,
)
const microsoftOAuthConfigured = oauthCredentialsConfigured(
  process.env.AZURE_AD_CLIENT_ID,
  process.env.AZURE_AD_CLIENT_SECRET,
)
const linkedinOAuthConfigured = oauthCredentialsConfigured(
  process.env.LINKEDIN_CLIENT_ID,
  process.env.LINKEDIN_CLIENT_SECRET,
)

/** Map NextAuth provider id → backend /api/auth/callback provider slug. */
const BACKEND_OAUTH_PROVIDER: Record<string, string> = {
  google: "google",
  github: "github",
  "microsoft-entra-id": "microsoft",
  linkedin: "linkedin",
}

const oauthProviders = [
  ...(googleOAuthConfigured
    ? [
        Google({
          clientId: process.env.GOOGLE_CLIENT_ID!,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET!,
        }),
      ]
    : []),
  ...(githubOAuthConfigured
    ? [
        GitHub({
          clientId: process.env.GITHUB_CLIENT_ID!,
          clientSecret: process.env.GITHUB_CLIENT_SECRET!,
        }),
      ]
    : []),
  ...(microsoftOAuthConfigured
    ? [
        MicrosoftEntraID({
          clientId: process.env.AZURE_AD_CLIENT_ID!,
          clientSecret: process.env.AZURE_AD_CLIENT_SECRET!,
          issuer: "https://login.microsoftonline.com/common/v2.0",
        }),
      ]
    : []),
  ...(linkedinOAuthConfigured
    ? [
        LinkedIn({
          clientId: process.env.LINKEDIN_CLIENT_ID!,
          clientSecret: process.env.LINKEDIN_CLIENT_SECRET!,
        }),
      ]
    : []),
]

// ── NextAuth config ───────────────────────────────────────────────────────────

export const { handlers, signIn, signOut, auth } = NextAuth({
  secret: nextAuthSecret,
  trustHost:
    process.env.AUTH_TRUST_HOST === "true" ||
    process.env.AUTH_TRUST_HOST === "1" ||
    isLocalEnv,
  providers: [
    ...oauthProviders,

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
    async jwt({ token, user, account, trigger, session }) {
      if (trigger === "update" && session) {
        const patch = session as {
          backendAccessToken?: string
          backendExpiresAt?: number
          backendUser?: BackendUser
        }
        if (patch.backendAccessToken) {
          token.backendAccessToken = patch.backendAccessToken
          token.backendExpiresAt = patch.backendExpiresAt
          delete token.error
        }
        if (patch.backendUser) {
          token.backendUser = patch.backendUser
        }
        return token
      }

      // ── Initial sign-in ────────────────────────────────────────────────────
      if (user && (account?.provider === "credentials" || account?.provider === "token")) {
        const backendUser = user as BackendAuthUser
        token.backendAccessToken = backendUser.backendAccessToken
        token.backendExpiresAt = backendUser.backendExpiresAt
        token.backendUser = backendUser.backendUser
        return token
      }

      // ── OAuth sign-in (Google / GitHub / Microsoft / LinkedIn) ──
      if (
        user &&
        account &&
        BACKEND_OAUTH_PROVIDER[account.provider]
      ) {
        const backendProvider = BACKEND_OAUTH_PROVIDER[account.provider]!
        const synced = await syncOAuthWithBackend(
          backendProvider,
          account.access_token ?? undefined,
          account.id_token ?? undefined,
          `${NEXTAUTH_URL}/api/auth/callback/${account.provider}`,
        )
        if (synced.ok) {
          token.backendAccessToken = synced.access_token
          token.backendExpiresAt = Date.now() + synced.expires_in * 1000
          token.backendUser = synced.user
        } else {
          token.error = synced.error
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
        backendExpiresAt: token.backendExpiresAt as number | undefined,
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
