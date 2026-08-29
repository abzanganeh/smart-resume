"use client"

import { Suspense, useEffect, useRef, useState, useTransition } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useSession } from "next-auth/react"
import { CheckCircle2, Loader2, Mail } from "lucide-react"
import { BrandLogo } from "@/components/brand/BrandLogo"
import { PRODUCT_NAME } from "@/lib/brand"
import { ThemeToggle } from "@/components/theme/ThemeToggle"
import { confirmEmailVerification } from "@/lib/auth/api"
import { friendlyAuthError } from "@/lib/auth/errors"
import { fetchMe } from "@/lib/auth/api"
import { postOnboardingDestination } from "@/lib/auth/onboarding"

function VerifyPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { update } = useSession()
  const token = searchParams.get("token")?.trim() ?? ""

  const [isPending, startTransition] = useTransition()
  const [error, setError] = useState<string | null>(null)
  const [verifiedEmail, setVerifiedEmail] = useState<string | null>(null)
  const [done, setDone] = useState(false)
  const startedRef = useRef(false)

  useEffect(() => {
    if (!token || startedRef.current) return
    startedRef.current = true
    startTransition(async () => {
      setError(null)
      try {
        const result = await confirmEmailVerification(token)
        setVerifiedEmail(result.email)
        setDone(true)
        try {
          const session = await update()
          const accessToken = session?.backendAccessToken
          if (accessToken) {
            const me = await fetchMe(accessToken)
            await update({ backendUser: me })
            router.replace(postOnboardingDestination(me))
            return
          }
        } catch {
          // Fall through to manual continue link.
        }
      } catch (err: unknown) {
        setError(friendlyAuthError((err as Error).message))
      }
    })
  }, [token])

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 flex items-center justify-center px-4 py-12 relative">
      <div className="absolute top-4 right-4">
        <ThemeToggle />
      </div>
      <div className="w-full max-w-md">
        <div className="text-center mb-8 flex flex-col items-center">
          <BrandLogo className="h-20 sm:h-24 w-auto max-w-[min(100%,420px)] mb-4" priority />
          <p className="text-slate-600 dark:text-slate-400 text-sm">Email verification</p>
        </div>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 shadow-2xl">
          {!token && (
            <div className="space-y-4 text-center">
              <Mail className="w-10 h-10 text-amber-700 dark:text-amber-400 mx-auto" />
              <p className="text-sm text-slate-600 dark:text-slate-400">
                This verification link is missing or incomplete. Open the link from your
                {PRODUCT_NAME} signup email, or request a new one in Settings.
              </p>
              <Link
                href="/settings"
                className="block w-full text-center bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors"
              >
                Go to Settings
              </Link>
            </div>
          )}

          {token && !done && !error && (
            <div className="flex flex-col items-center gap-3 py-6 text-slate-600 dark:text-slate-400">
              <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
              <p className="text-sm">Confirming your email…</p>
            </div>
          )}

          {error && (
            <div className="space-y-4">
              <div className="p-3 rounded-lg bg-red-50 dark:bg-red-950/60 border border-red-200 dark:border-red-800 text-red-700 dark:text-red-300 text-sm">
                {error}
              </div>
              <Link
                href="/settings"
                className="block w-full text-center bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors"
              >
                Resend verification email
              </Link>
            </div>
          )}

          {done && (
            <div className="space-y-5 text-center">
              <CheckCircle2 className="w-10 h-10 text-emerald-600 dark:text-emerald-400 mx-auto" />
              <div className="p-3 rounded-lg bg-emerald-50 dark:bg-emerald-950/60 border border-emerald-200 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 text-sm">
                {verifiedEmail ? (
                  <>
                    <strong>{verifiedEmail}</strong> is verified. Your free credits are
                    unlocked.
                  </>
                ) : (
                  <>Your email is verified. Your free credits are unlocked.</>
                )}
              </div>
              <Link
                href="/dashboard"
                className="block w-full text-center bg-amber-400 text-slate-900 font-semibold py-2.5 rounded-lg hover:bg-amber-300 transition-colors"
              >
                Continue to dashboard
              </Link>
            </div>
          )}

          {isPending && token && !done && !error && null}
        </div>
      </div>
    </main>
  )
}

export default function VerifyPage() {
  return (
    <Suspense
      fallback={
        <main className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
          <Loader2 className="h-8 w-8 animate-spin text-amber-700 dark:text-amber-400" />
        </main>
      }
    >
      <VerifyPageContent />
    </Suspense>
  )
}
