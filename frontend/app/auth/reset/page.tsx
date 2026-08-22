"use client"

import { Suspense, useState, useTransition } from "react"
import Link from "next/link"
import { useSearchParams } from "next/navigation"
import { Eye, EyeOff, Loader2, Lock, Mail } from "lucide-react"
import zxcvbn from "zxcvbn"
import { BrandLogo } from "@/components/brand/BrandLogo"
import { PRODUCT_NAME } from "@/lib/brand"
import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { forgotPassword, resetPassword } from "@/lib/auth/api"
import { friendlyAuthError } from "@/lib/auth/errors"

const STRENGTH_LABELS = ["Very weak", "Weak", "Fair", "Strong", "Very strong"]
const STRENGTH_COLORS = [
  "bg-red-500",
  "bg-orange-500",
  "bg-yellow-500",
  "bg-emerald-500",
  "bg-emerald-600",
]

function ResetPageContent() {
  const searchParams = useSearchParams()
  const token = searchParams.get("token")?.trim() ?? ""
  const emailFromQuery = searchParams.get("email") ?? ""

  const [isPending, startTransition] = useTransition()
  const [email, setEmail] = useState(emailFromQuery)
  const [password, setPassword] = useState("")
  const [confirm, setConfirm] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [strength, setStrength] = useState(0)
  const [error, setError] = useState<string | null>(null)
  const [sent, setSent] = useState(false)
  const [debugResetUrl, setDebugResetUrl] = useState<string | null>(null)
  const [resetDone, setResetDone] = useState(false)

  function onPasswordChange(val: string) {
    setPassword(val)
    setStrength(zxcvbn(val, [email]).score)
  }

  function handleRequest(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setDebugResetUrl(null)
    startTransition(async () => {
      try {
        const result = await forgotPassword(email.trim())
        setDebugResetUrl(result.debug_reset_url ?? null)
        setSent(true)
      } catch (err: unknown) {
        setError(friendlyAuthError((err as Error).message))
      }
    })
  }

  function handleReset(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError("Passwords do not match.")
      return
    }
    if (password.length < 10 || strength < 3) {
      setError("Please choose a stronger password (score ≥ Strong).")
      return
    }
    startTransition(async () => {
      try {
        await resetPassword({ token, new_password: password })
        setResetDone(true)
      } catch (err: unknown) {
        setError(friendlyAuthError((err as Error).message))
      }
    })
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 flex items-center justify-center px-4 py-12 relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md">
        <div className="text-center mb-8 flex flex-col items-center">
          <BrandLogo className="h-20 sm:h-24 w-auto max-w-[min(100%,420px)] mb-4" priority />
          <p className="text-slate-600 dark:text-slate-400 text-sm">
            {token ? "Choose a new password" : "Reset your password"}
          </p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 shadow-2xl">
          {error && (
            <div className="mb-5 p-3 rounded-lg bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
              {error}
            </div>
          )}

          {!token && sent && (
            <div className="space-y-5">
              <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-sm">
                If an account exists for that email, we sent a reset link. Check
                Mailpit at{" "}
                <a
                  href="http://127.0.0.1:38025"
                  className="underline underline-offset-2"
                  target="_blank"
                  rel="noreferrer"
                >
                  http://127.0.0.1:38025
                </a>{" "}
                locally, or your inbox. The link expires in one hour.
              </div>
              {debugResetUrl && (
                <p className="text-sm text-slate-600 dark:text-slate-400 break-all">
                  Local reset link:{" "}
                  <a
                    href={debugResetUrl}
                    className="text-amber-700 dark:text-amber-400 underline underline-offset-2"
                  >
                    {debugResetUrl}
                  </a>
                </p>
              )}
              <Link
                href="/auth"
                className="block w-full text-center text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
              >
                ← Back to sign in
              </Link>
            </div>
          )}

          {!token && !sent && (
            <form onSubmit={handleRequest} className="space-y-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                Enter the email on your {PRODUCT_NAME} account. We will send a
                link so you can choose a new password.
              </p>
              <div>
                <label
                  htmlFor="reset-email"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5"
                >
                  Email address
                </label>
                <div className="relative">
                  <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                  <input
                    id="reset-email"
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
              <button
                type="submit"
                disabled={isPending}
                className="w-full bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2 mt-2"
              >
                {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Send reset link
              </button>
              <Link
                href="/auth"
                className="block w-full text-center text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
              >
                ← Back to sign in
              </Link>
            </form>
          )}

          {token && resetDone && (
            <div className="space-y-5">
              <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-sm">
                Your password has been updated. Sign in with your new password.
              </div>
              <Link
                href="/auth"
                className="block w-full text-center bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors"
              >
                Sign in
              </Link>
            </div>
          )}

          {token && !resetDone && (
            <form onSubmit={handleReset} className="space-y-4">
              <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
                Choose a new password for your {PRODUCT_NAME} account. This
                signs you out of other devices.
              </p>
              <div>
                <label
                  htmlFor="reset-password"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5"
                >
                  New password{" "}
                  <span className="text-slate-600 dark:text-slate-400 font-normal">
                    (min 10 chars)
                  </span>
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                  <input
                    id="reset-password"
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={10}
                    autoComplete="new-password"
                    placeholder="••••••••••"
                    value={password}
                    onChange={(e) => onPasswordChange(e.target.value)}
                    className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-10 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300"
                    aria-label={showPassword ? "Hide password" : "Show password"}
                  >
                    {showPassword ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                  </button>
                </div>
                {password.length > 0 && (
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
                          strength >= 3
                            ? "text-emerald-700 dark:text-emerald-400"
                            : strength >= 2
                              ? "text-yellow-700 dark:text-yellow-400"
                              : "text-red-700 dark:text-red-400"
                        }`}
                      >
                        {STRENGTH_LABELS[strength]}
                      </span>
                    </p>
                  </div>
                )}
              </div>
              <div>
                <label
                  htmlFor="reset-password-confirm"
                  className="block text-sm font-medium text-slate-700 dark:text-slate-300 mb-1.5"
                >
                  Confirm new password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
                  <input
                    id="reset-password-confirm"
                    type={showPassword ? "text" : "password"}
                    required
                    minLength={10}
                    autoComplete="new-password"
                    placeholder="••••••••••"
                    value={confirm}
                    onChange={(e) => setConfirm(e.target.value)}
                    className="w-full bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-lg pl-10 pr-4 py-2.5 text-slate-900 dark:text-white placeholder:text-slate-500 dark:placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50"
                  />
                </div>
              </div>
              <button
                type="submit"
                disabled={isPending}
                className="w-full bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors disabled:opacity-60 flex items-center justify-center gap-2 mt-2"
              >
                {isPending && <Loader2 className="w-4 h-4 animate-spin" />}
                Update password
              </button>
              <Link
                href="/auth/reset"
                className="block w-full text-center text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
              >
                Request a new reset link
              </Link>
            </form>
          )}
        </div>
      </div>
    </main>
  )
}

export default function ResetPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex items-center justify-center px-4">
          <Loader2 className="h-8 w-8 animate-spin text-amber-700 dark:text-amber-400" />
        </main>
      }
    >
      <ResetPageContent />
    </Suspense>
  )
}
