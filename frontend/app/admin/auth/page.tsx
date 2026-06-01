"use client"

import { useState, useTransition } from "react"
import { useRouter, useSearchParams } from "next/navigation"
import { Lock, Mail, Shield, Loader2, Eye, EyeOff } from "lucide-react"
import { adminLogin, adminVerifyTotp } from "@/lib/admin/api"
import { storeAdminSession } from "@/lib/admin/session"

type Step = "credentials" | "totp"
type AuthHint = {
  enrollment_qr_svg?: string | null
  enrollment_uri?: string | null
  enrollment_secret?: string | null
}

// ── Admin Auth Page ───────────────────────────────────────────────────────────

export default function AdminAuthPage() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const reason = searchParams.get("reason")

  const [step, setStep] = useState<Step>("credentials")
  const [isPending, startTransition] = useTransition()

  // Credentials step
  const [email, setEmail] = useState("")
  const [password, setPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)

  // TOTP step
  const [challengeToken, setChallengeToken] = useState("")
  const [totpCode, setTotpCode] = useState("")
  const [authHint, setAuthHint] = useState<AuthHint | null>(null)

  const [error, setError] = useState<string | null>(
    reason === "expired" ? "Your admin session has expired. Please sign in again." : null,
  )

  // ── Step 1: Submit credentials ────────────────────────────────────────────

  function handleCredentials(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    startTransition(async () => {
      try {
        const res = await adminLogin(email, password)
        if (res.status === "enrollment_required") {
          setAuthHint({
            enrollment_qr_svg: res.enrollment_qr_svg ?? null,
            enrollment_uri: res.enrollment_uri ?? null,
            enrollment_secret: res.enrollment_secret ?? null,
          })
          setError(
            "TOTP enrollment required for this admin account. Scan the QR, then enter the 6-digit code.",
          )
        } else {
          setAuthHint(null)
        }
        if (!res.challenge_token) {
          setError("Authentication challenge missing. Please retry sign-in.")
          return
        }
        setChallengeToken(res.challenge_token)
        setStep("totp")
      } catch (err) {
        setError(friendlyError(err))
      }
    })
  }

  // ── Step 2: Verify TOTP ───────────────────────────────────────────────────

  function handleTotp(e: React.FormEvent) {
    e.preventDefault()
    if (totpCode.length !== 6) {
      setError("Enter the 6-digit code from your authenticator app.")
      return
    }
    setError(null)
    startTransition(async () => {
      try {
        const res = await adminVerifyTotp(challengeToken, totpCode)
        await storeAdminSession(res.access_token, res.admin, res.expires_in)
        router.replace("/admin/plans")
      } catch (err) {
        setError(friendlyError(err))
      }
    })
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <div className="w-full max-w-sm">
        {/* Header */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-12 h-12 rounded-full bg-red-900/40 border border-red-700/50 mb-4">
            <Shield className="w-6 h-6 text-red-400" />
          </div>
          <h1 className="text-xl font-semibold text-white">Admin Sign-in</h1>
          <p className="text-sm text-slate-400 mt-1">
            {step === "credentials"
              ? "Enter your admin credentials"
              : "Two-factor authentication required"}
          </p>
        </div>

        {/* Step indicator */}
        <div className="flex items-center gap-2 mb-6">
          <StepDot active={true} done={step === "totp"} label="1" />
          <div
            className={`flex-1 h-0.5 transition-colors ${step === "totp" ? "bg-amber-500" : "bg-slate-700"}`}
          />
          <StepDot active={step === "totp"} done={false} label="2" />
        </div>

        {/* Error */}
        {error && (
          <div className="mb-4 bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
            {error}
          </div>
        )}

        {/* ── Credentials form ─────────────────────────────────────────── */}
        {step === "credentials" && (
          <form onSubmit={handleCredentials} className="space-y-4">
            <div>
              <label className="block text-sm text-slate-300 mb-1.5" htmlFor="email">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  id="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"
                  placeholder="admin@example.com"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm text-slate-300 mb-1.5" htmlFor="password">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg pl-10 pr-10 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"
                  placeholder="••••••••••"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword((v) => !v)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-slate-300"
                  tabIndex={-1}
                >
                  {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            <button
              type="submit"
              disabled={isPending}
              className="w-full bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
            >
              {isPending ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : null}
              Continue
            </button>
          </form>
        )}

        {/* ── TOTP form ─────────────────────────────────────────────────── */}
        {step === "totp" && (
          <form onSubmit={handleTotp} className="space-y-4">
            {authHint && (
              <div className="bg-slate-900 border border-slate-700 rounded-lg p-3 space-y-2">
                <p className="text-xs text-slate-400">
                  First-time setup: scan this QR code in your authenticator app.
                </p>
                {authHint.enrollment_qr_svg ? (
                  <div
                    className="bg-white rounded-md p-2 inline-block"
                    dangerouslySetInnerHTML={{ __html: authHint.enrollment_qr_svg }}
                  />
                ) : authHint.enrollment_uri ? (
                  <code className="text-[11px] text-amber-300 break-all block">
                    {authHint.enrollment_uri}
                  </code>
                ) : null}
                {authHint.enrollment_secret ? (
                  <p className="text-[11px] text-slate-500">
                    Secret: <code>{authHint.enrollment_secret}</code>
                  </p>
                ) : null}
              </div>
            )}
            <div>
              <label className="block text-sm text-slate-300 mb-1.5" htmlFor="totp">
                Authenticator code
              </label>
              <input
                id="totp"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                autoComplete="one-time-code"
                autoFocus
                required
                value={totpCode}
                onChange={(e) => setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6))}
                className="w-full bg-slate-900 border border-slate-700 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 tracking-widest text-center text-lg font-mono focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"
                placeholder="000000"
              />
              <p className="text-xs text-slate-500 mt-1.5 text-center">
                Open your authenticator app and enter the 6-digit code.
              </p>
            </div>

            <button
              type="submit"
              disabled={isPending || totpCode.length !== 6}
              className="w-full bg-amber-600 hover:bg-amber-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium py-2.5 rounded-lg text-sm transition-colors flex items-center justify-center gap-2"
            >
              {isPending ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              Verify & Sign in
            </button>

            <button
              type="button"
              onClick={() => {
                setStep("credentials")
                setTotpCode("")
                setAuthHint(null)
                setError(null)
              }}
              className="w-full text-slate-500 hover:text-slate-300 text-sm py-2 transition-colors"
            >
              ← Back
            </button>
          </form>
        )}

        {/* Security note */}
        <p className="text-center text-xs text-slate-600 mt-6">
          Sessions expire after 1 hour and are IP-bound.
        </p>
      </div>
    </div>
  )
}

// ── Step dot helper ───────────────────────────────────────────────────────────

function StepDot({ active, done, label }: { active: boolean; done: boolean; label: string }) {
  return (
    <div
      className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold border-2 transition-colors ${
        done
          ? "bg-amber-600 border-amber-600 text-white"
          : active
            ? "border-amber-500 text-amber-400"
            : "border-slate-700 text-slate-600"
      }`}
    >
      {label}
    </div>
  )
}

// ── Error formatter ───────────────────────────────────────────────────────────

function friendlyError(err: unknown): string {
  if (err instanceof Error) {
    const m = err.message
    if (m === "invalid_credentials") return "Invalid email or password."
    if (m === "account_suspended") return "This admin account is suspended."
    if (m === "invalid_totp") return "Incorrect code. Try again."
    if (m === "challenge_expired") return "Challenge expired. Please start over."
    return m
  }
  return "Something went wrong."
}
