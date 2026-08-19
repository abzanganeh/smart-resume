"use client"

import { Suspense, useEffect, useRef, useState, useTransition, type ReactElement } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { signIn, signOut, useSession, getProviders } from "next-auth/react"
import { Eye, EyeOff, Loader2, Lock, Mail, User } from "lucide-react"
import zxcvbn from "zxcvbn"
import { BrandLogo } from "@/components/brand/BrandLogo"
import { ThemeToggle } from "@/components/theme/ThemeToggle"
import {
  fetchMe,
  loginUser,
  registerUser,
  verify2fa,
  type TfaRequired,
} from "@/lib/auth/api"
import { isStaleAuthError } from "@/lib/auth/staleSession"
import { resolveAuthReturnUrl, saveAuthReturnUrl } from "@/lib/auth/returnUrl"
import { friendlyAuthError } from "@/lib/auth/errors"
import {
  captureExtensionHandoffFromParams,
  captureExtensionHandoffFromUrl,
} from "@/lib/extensionHandoff"

// ── Constants ─────────────────────────────────────────────────────────────────

const TOS_VERSION = "2024-01"

const STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Strong", "Very strong"]
const STRENGTH_COLORS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-yellow-500",
  "bg-emerald-500",
  "bg-emerald-600",
]

type View = "login" | "register" | "2fa"

type SsoOption = {
  id: string
  label: string
  Icon: () => ReactElement
}

const SSO_PROVIDER_OPTIONS: SsoOption[] = [
  { id: "google", label: "Google", Icon: GoogleIcon },
  { id: "github", label: "GitHub", Icon: GitHubIcon },
  { id: "microsoft-entra-id", label: "Microsoft", Icon: MicrosoftIcon },
  { id: "linkedin", label: "LinkedIn", Icon: LinkedInIcon },
]

// ── Auth Page ─────────────────────────────────────────────────────────────────

function AuthPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { data: session, status } = useSession()

  // Derive initial 2FA state directly from URL params (avoids setState-in-effect warning)
  const errorParam = searchParams.get("error") ?? ""
  const modeParam = searchParams.get("mode")
  const initialTfa: TfaRequired | null = errorParam.startsWith("2fa_required:")
    ? (() => {
        const parts = errorParam.split(":")
        return { code: "2fa_required" as const, challenge_token: parts[1], expires_in: Number(parts[2] ?? 300) }
      })()
    : null
  const initialView: View = initialTfa ? "2fa" : modeParam === "register" ? "register" : "login"
  const initialError: string | null = !initialTfa && errorParam ? friendlyAuthError(errorParam) : null

  const [view, setView] = useState<View>(initialView)
  const [isPending, startTransition] = useTransition()

  // Form fields
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [displayName, setDisplayName] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [tosAccepted, setTosAccepted] = useState(false)
  const [privacyAccepted, setPrivacyAccepted] = useState(false)
  const [marketingOptIn, setMarketingOptIn] = useState(false)

  // 2FA state
  const [tfaChallenge, setTfaChallenge] = useState<TfaRequired | null>(initialTfa)
  const [totpCode, setTotpCode] = useState("")
  const [recoveryCode, setRecoveryCode] = useState("")
  const [showRecovery, setShowRecovery] = useState(false)

  // UI state
  const [error, setError] = useState<string | null>(initialError)
  const [errorCode, setErrorCode] = useState<string | null>(null)
  const [successMsg, setSuccessMsg] = useState<string | null>(null)
  const [strength, setStrength] = useState(0)
  const [ssoProviders, setSsoProviders] = useState<string[]>([])
  const postAuthRedirectRef = useRef(false)

  useEffect(() => {
    getProviders().then((providers) => {
      if (!providers) return
      setSsoProviders(
        SSO_PROVIDER_OPTIONS.filter(({ id }) => Boolean(providers[id])).map(({ id }) => id),
      )
    })
  }, [])

  // Drop ?error= from the URL after first paint so a failed OAuth round-trip does
  // not keep showing the banner on refresh or block the next sign-in attempt.
  useEffect(() => {
    if (!errorParam || typeof window === "undefined") return
    const url = new URL(window.location.href)
    if (!url.searchParams.has("error")) return
    url.searchParams.delete("error")
    window.history.replaceState(
      window.history.state,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    )
  }, [errorParam])

  // Persist extension JD handoff before OAuth round-trips strip nested query params.
  useEffect(() => {
    const callbackUrl = searchParams.get("callbackUrl")
    if (callbackUrl) captureExtensionHandoffFromUrl(callbackUrl)
    captureExtensionHandoffFromParams(searchParams)
  }, [searchParams])

  function doRedirect(
    callbackUrl: string,
    onboardingCompletedAt: string | null | undefined,
  ) {
    const dest = resolveAuthReturnUrl(callbackUrl)
    if (dest && dest !== "/auth" && onboardingCompletedAt) {
      router.replace(dest)
    } else if (!onboardingCompletedAt) {
      // Keep extension / deep-link return paths across onboarding.
      saveAuthReturnUrl(dest !== "/dashboard" ? dest : undefined)
      router.replace("/onboarding")
    } else {
      router.replace("/dashboard")
    }
  }

  // Redirect only when the backend token still resolves to a live user row.
  useEffect(() => {
    if (status !== "authenticated") {
      postAuthRedirectRef.current = false
      return
    }

    if (typeof window !== "undefined" && window.location.pathname !== "/auth") {
      return
    }

    if (session?.backendAccessToken) {
      if (postAuthRedirectRef.current) return
      void fetchMe(session.backendAccessToken)
        .then((user) => {
          if (postAuthRedirectRef.current) return
          postAuthRedirectRef.current = true
          const callbackUrl = searchParams.get("callbackUrl") ?? ""
          doRedirect(callbackUrl, user.onboarding_completed_at)
        })
        .catch((err: unknown) => {
          const message = err instanceof Error ? err.message : ""
          if (isStaleAuthError(message)) {
            void signOut({ redirect: false })
          }
        })
      return
    }

    if (session?.error) {
      showError(session.error)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [status, session])

  function showError(code: string) {
    setErrorCode(code)
    setError(friendlyAuthError(code))
  }

  function clearError() {
    setError(null)
    setErrorCode(null)
  }

  function onPasswordChange(val: string) {
    setPassword(val)
    if (view === "register") {
      setStrength(zxcvbn(val, [email, displayName]).score)
    }
  }

  // ── Registration ────────────────────────────────────────────────────────────

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    clearError()
    if (!tosAccepted || !privacyAccepted) {
      setError("You must accept the Terms of Service and Privacy Policy.")
      return
    }
    if (strength < 2) {
      setError("Please choose a stronger password (score ≥ Fair).")
      return
    }
    startTransition(async () => {
      try {
        const data = await registerUser({
          email,
          password,
          display_name: displayName || undefined,
          accepted_tos_version: TOS_VERSION,
          marketing_opt_in: marketingOptIn,
        })
        // Create NextAuth session from the backend tokens
        await signIn("token", {
          redirect: false,
          access_token: data.access_token,
          expires_in: String(data.expires_in),
          user_json: JSON.stringify(data.user),
        })
        setSuccessMsg("Account created! Check your email to verify your address.")
        // Session update will trigger the redirect effect above
      } catch (err: unknown) {
        showError((err as Error).message)
      }
    })
  }

  // ── Login ───────────────────────────────────────────────────────────────────

  async function handleLogin(e: React.FormEvent) {
    e.preventDefault()
    clearError()
    startTransition(async () => {
      try {
        const result = await loginUser({ email, password })

        if ("code" in result && result.code === "2fa_required") {
          setTfaChallenge(result)
          setView("2fa")
          return
        }

        // Successful login — create NextAuth session
        const authResult = result as import("@/lib/auth/api").AuthSuccess
        await signIn("token", {
          redirect: false,
          access_token: authResult.access_token,
          expires_in: String(authResult.expires_in),
          user_json: JSON.stringify(authResult.user),
        })
        // The session effect above handles the redirect
      } catch (err: unknown) {
        showError((err as Error).message)
      }
    })
  }

  // ── 2FA verification ────────────────────────────────────────────────────────

  async function handle2fa(e: React.FormEvent) {
    e.preventDefault()
    clearError()
    if (!tfaChallenge) return
    startTransition(async () => {
      try {
        const data = await verify2fa({
          challenge_token: tfaChallenge.challenge_token,
          code: showRecovery ? undefined : totpCode || undefined,
          recovery_code: showRecovery ? recoveryCode || undefined : undefined,
        })
        await signIn("token", {
          redirect: false,
          access_token: data.access_token,
          expires_in: String(data.expires_in),
          user_json: JSON.stringify(data.user),
        })
      } catch (err: unknown) {
        showError((err as Error).message)
      }
    })
  }

  // ── SSO ─────────────────────────────────────────────────────────────────────

  function stripAuthErrorFromUrl() {
    if (typeof window === "undefined") return
    const url = new URL(window.location.href)
    if (!url.searchParams.has("error")) return
    url.searchParams.delete("error")
    window.history.replaceState(
      window.history.state,
      "",
      `${url.pathname}${url.search}${url.hash}`,
    )
  }

  function handleSSO(provider: string) {
    clearError()
    stripAuthErrorFromUrl()
    const callbackUrl = resolveAuthReturnUrl(
      searchParams.get("callbackUrl"),
      "/dashboard",
    )
    saveAuthReturnUrl(callbackUrl)
    signIn(provider, { callbackUrl })
  }

  // ── Render ──────────────────────────────────────────────────────────────────
  // Do not block on useSession "loading" — LAN/dev hosts often mismatch
  // NEXTAUTH_URL and leave the client fetch hanging. proxy.ts already redirects
  // signed-in users away from /auth; show the form immediately.

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 flex items-center justify-center px-4 py-12 relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md">
        {/* Logo / brand */}
        <div className="text-center mb-8 flex flex-col items-center">
          <BrandLogo className="h-20 sm:h-24 w-auto max-w-[min(100%,420px)] mb-4" priority />
          <p className="text-slate-600 dark:text-slate-400 text-sm">
            {view === "register"
              ? "Create your free account"
              : view === "2fa"
              ? "Two-factor authentication"
              : "Welcome back"}
          </p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 shadow-2xl">
          {/* Error / success banners */}
          {error && (
            <div className="mb-5 p-3 rounded-lg bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm space-y-2">
              <p>{error}</p>
              {(errorCode === "email_registered_with_sso" ||
                errorCode === "sso_sign_in_required") && (
                <button
                  type="button"
                  onClick={() => {
                    setView("login")
                    clearError()
                  }}
                  className="text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 underline underline-offset-2"
                >
                  Go to Sign in
                </button>
              )}
            </div>
          )}
          {successMsg && (
            <div className="mb-5 p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-sm">
              {successMsg}
            </div>
          )}

          {/* ── 2FA view ──────────────────────────────────────────────── */}
          {view === "2fa" && (
            <form onSubmit={handle2fa} className="space-y-5">
              <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed">
                Your account has two-factor authentication enabled. Enter your
                6-digit TOTP code from your authenticator app.
              </p>

              {!showRecovery ? (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    TOTP code
                  </label>
                  <input
                    type="text"
                    inputMode="numeric"
                    maxLength={6}
                    placeholder="000000"
                    value={totpCode}
                    onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, ""))}
                    className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-4 py-2.5 text-slate-900 dark:text-white text-center text-xl tracking-widest placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                    autoFocus
                  />
                </div>
              ) : (
                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Recovery code
                  </label>
                  <input
                    type="text"
                    placeholder="xxxx-xxxx"
                    value={recoveryCode}
                    onChange={(e) => setRecoveryCode(e.target.value)}
                    className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg px-4 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                    autoFocus
                  />
                </div>
              )}

              <button
                type="submit"
                disabled={isPending}
                className="w-full bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2"
              >
                {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Verify
              </button>

              <button
                type="button"
                onClick={() => {
                  setShowRecovery((v) => !v)
                  setError(null)
                }}
                className="w-full text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 transition-colors"
              >
                {showRecovery ? "Use TOTP code instead" : "Use a recovery code instead"}
              </button>

              <button
                type="button"
                onClick={() => {
                  setView("login")
                  setTfaChallenge(null)
                  setTotpCode("")
                  setRecoveryCode("")
                  setError(null)
                }}
                className="w-full text-sm text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300 transition-colors"
              >
                ← Back to login
              </button>
            </form>
          )}

          {/* ── Login / Register views ─────────────────────────────────── */}
          {view !== "2fa" && (
            <>
              {/* View toggle */}
              <div className="flex gap-1 p-1 bg-slate-100 dark:bg-slate-800 rounded-lg mb-6">
                {(["login", "register"] as const).map((v) => (
                  <button
                    key={v}
                    type="button"
                    onClick={() => {
                      setView(v)
                      clearError()
                      setSuccessMsg(null)
                    }}
                    className={`flex-1 py-2 text-sm font-medium rounded-md transition-colors ${
                      view === v
                        ? "bg-slate-200 dark:bg-slate-700 text-slate-900 dark:text-white"
                        : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                    }`}
                  >
                    {v === "login" ? "Sign in" : "Register"}
                  </button>
                ))}
              </div>

              {/* SSO buttons — only when real OAuth credentials are configured */}
              {ssoProviders.length > 0 && (
                <div className="space-y-3 mb-6">
                  {SSO_PROVIDER_OPTIONS.filter(({ id }) => ssoProviders.includes(id)).map(
                    ({ id, label, Icon }) => (
                      <button
                        key={id}
                        type="button"
                        onClick={() => handleSSO(id)}
                        className="w-full flex items-center justify-center gap-3 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 py-2.5 rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors text-sm font-medium"
                      >
                        <Icon />
                        Continue with {label}
                      </button>
                    ),
                  )}
                </div>
              )}

              {ssoProviders.length > 0 && (
              <div className="relative mb-6">
                <div className="absolute inset-0 flex items-center">
                  <div className="w-full border-t border-slate-300 dark:border-slate-700" />
                </div>
                <div className="relative flex justify-center text-xs">
                  <span className="bg-white dark:bg-slate-900 px-3 text-slate-600 dark:text-slate-400">or continue with email</span>
                </div>
              </div>
              )}

              {/* Email / password form */}
              <form
                onSubmit={view === "register" ? handleRegister : handleLogin}
                className="space-y-4"
              >
                {view === "register" && (
                  <div>
                    <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                      Display name <span className="text-slate-600 dark:text-slate-400">(optional)</span>
                    </label>
                    <div className="relative">
                      <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                      <input
                        type="text"
                        autoComplete="name"
                        placeholder="Your name"
                        value={displayName}
                        onChange={(e) => setDisplayName(e.target.value)}
                        className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                      />
                    </div>
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Email address
                  </label>
                  <div className="relative">
                    <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                    <input
                      type="email"
                      required
                      autoComplete="email"
                      placeholder="you@example.com"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                      className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5">
                    Password
                    {view === "register" && (
                      <span className="text-slate-600 dark:text-slate-400 font-normal ml-1">(min 10 chars)</span>
                    )}
                  </label>
                  <div className="relative">
                    <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                    <input
                      type={showPassword ? "text" : "password"}
                      required
                      minLength={view === "register" ? 10 : 1}
                      autoComplete={view === "register" ? "new-password" : "current-password"}
                      placeholder="••••••••••"
                      value={password}
                      onChange={(e) => onPasswordChange(e.target.value)}
                      className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-10 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                    />
                    <button
                      type="button"
                      onClick={() => setShowPassword((v) => !v)}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300"
                    >
                      {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                    </button>
                  </div>

                  {/* zxcvbn strength bar — register only */}
                  {view === "register" && password.length > 0 && (
                    <div className="mt-2 space-y-1">
                      <div className="flex gap-1">
                        {[0, 1, 2, 3, 4].map((i) => (
                          <div
                            key={i}
                            className={`h-1 flex-1 rounded-full transition-colors ${
                              i <= strength ? STRENGTH_COLORS[strength] : "bg-slate-200 dark:bg-slate-700"
                            }`}
                          />
                        ))}
                      </div>
                      <p className="text-xs text-slate-600 dark:text-slate-400">
                        Strength:{" "}
                        <span
                          className={`font-medium ${
                            strength >= 3 ? "text-emerald-700 dark:text-emerald-400" : strength >= 2 ? "text-yellow-700 dark:text-yellow-400" : "text-red-700 dark:text-red-400"
                          }`}
                        >
                          {STRENGTH_LABELS[strength]}
                        </span>
                      </p>
                    </div>
                  )}
                </div>

                {/* Register: consent checkboxes */}
                {view === "register" && (
                  <div className="space-y-3 pt-1">
                    <label className="flex items-start gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={tosAccepted}
                        onChange={(e) => setTosAccepted(e.target.checked)}
                        className="mt-0.5 accent-amber-400"
                        required
                      />
                      <span className="text-sm text-slate-600 dark:text-slate-400">
                        I agree to the{" "}
                        <a href="/legal/terms" target="_blank" className="text-amber-700 dark:text-amber-400 hover:underline">
                          Terms of Service
                        </a>{" "}
                        <span className="text-red-700 dark:text-red-400">*</span>
                      </span>
                    </label>
                    <label className="flex items-start gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={privacyAccepted}
                        onChange={(e) => setPrivacyAccepted(e.target.checked)}
                        className="mt-0.5 accent-amber-400"
                        required
                      />
                      <span className="text-sm text-slate-600 dark:text-slate-400">
                        I have read the{" "}
                        <a href="/legal/privacy" target="_blank" className="text-amber-700 dark:text-amber-400 hover:underline">
                          Privacy Policy
                        </a>{" "}
                        <span className="text-red-700 dark:text-red-400">*</span>
                      </span>
                    </label>
                    <label className="flex items-start gap-2.5 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={marketingOptIn}
                        onChange={(e) => setMarketingOptIn(e.target.checked)}
                        className="mt-0.5 accent-amber-400"
                      />
                      <span className="text-sm text-slate-600 dark:text-slate-400">
                        Send me product updates and tips (optional)
                      </span>
                    </label>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={isPending}
                  className="w-full bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2 mt-2"
                >
                  {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                  {view === "register" ? "Create account" : "Sign in"}
                </button>
              </form>
            </>
          )}
        </div>

        <p className="text-center text-slate-600 dark:text-slate-400 text-xs mt-6">
          By using TalioCV you agree to our{" "}
          <a href="/legal/terms" className="hover:text-slate-800 dark:hover:text-slate-300 underline underline-offset-2">
            Terms
          </a>{" "}
          and{" "}
          <a href="/legal/privacy" className="hover:text-slate-800 dark:hover:text-slate-300 underline underline-offset-2">
            Privacy Policy
          </a>
          .
        </p>
      </div>
    </main>
  )
}

export default function AuthPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex items-center justify-center px-4">
          <Loader2 className="h-8 w-8 animate-spin text-amber-700 dark:text-amber-400" />
        </main>
      }
    >
      <AuthPageContent />
    </Suspense>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function GitHubIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5 fill-current" aria-hidden="true">
      <path d="M12 2C6.477 2 2 6.484 2 12.017c0 4.425 2.865 8.18 6.839 9.504.5.092.682-.217.682-.483 0-.237-.008-.868-.013-1.703-2.782.605-3.369-1.343-3.369-1.343-.454-1.158-1.11-1.466-1.11-1.466-.908-.62.069-.608.069-.608 1.003.07 1.531 1.032 1.531 1.032.892 1.53 2.341 1.088 2.91.832.092-.647.35-1.088.636-1.338-2.22-.253-4.555-1.113-4.555-4.951 0-1.093.39-1.988 1.029-2.688-.103-.253-.446-1.272.098-2.65 0 0 .84-.27 2.75 1.026A9.564 9.564 0 0112 6.844c.85.004 1.705.115 2.504.337 1.909-1.296 2.747-1.027 2.747-1.027.546 1.379.202 2.398.1 2.651.64.7 1.028 1.595 1.028 2.688 0 3.848-2.339 4.695-4.566 4.943.359.309.678.92.678 1.855 0 1.338-.012 2.419-.012 2.747 0 .268.18.58.688.482A10.019 10.019 0 0022 12.017C22 6.484 17.522 2 12 2z" />
    </svg>
  )
}

function GoogleIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true">
      <path
        fill="#4285F4"
        d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"
      />
      <path
        fill="#34A853"
        d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"
      />
      <path
        fill="#FBBC05"
        d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"
      />
      <path
        fill="#EA4335"
        d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"
      />
    </svg>
  )
}

function MicrosoftIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true">
      <path fill="#F25022" d="M3 3h9v9H3z" />
      <path fill="#7FBA00" d="M12 3h9v9h-9z" />
      <path fill="#00A4EF" d="M3 12h9v9H3z" />
      <path fill="#FFB900" d="M12 12h9v9h-9z" />
    </svg>
  )
}

function LinkedInIcon() {
  return (
    <svg viewBox="0 0 24 24" className="w-5 h-5" aria-hidden="true">
      <path
        fill="#0A66C2"
        d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.062 2.062 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
      />
    </svg>
  )
}
