"use client"

import { useEffect, useState } from "react"
import { useSession } from "next-auth/react"
import Link from "next/link"
import { CheckCircle2, Loader2, Sparkles } from "lucide-react"
import { getSubscriptionCurrent, type SubscriptionCurrentResponse } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"

const POLL_INTERVAL_MS = 2_500
const POLL_TIMEOUT_MS = 30_000

export default function BillingSuccessPage() {
  const { data: session, status } = useSession()
  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [timedOut, setTimedOut] = useState(false)

  useEffect(() => {
    const token = session?.backendAccessToken
    if (!token) {
      const timeout = window.setTimeout(() => {
        setLoading(false)
      }, 0)
      return () => window.clearTimeout(timeout)
    }

    if (status !== "authenticated") {
      return
    }

    let cancelled = false
    const startedAt = Date.now()

    const poll = async () => {
      if (cancelled) return
      try {
        const data = await getSubscriptionCurrent(token)
        if (cancelled) return
        setCurrent(data)

        const sub = data.subscription
        const activated = !!sub && isSubscriptionActive(sub.status)

        if (activated) {
          setTimedOut(false)
          setLoading(false)
          return
        }
      } catch {
        if (cancelled) return
      }

      if (Date.now() - startedAt >= POLL_TIMEOUT_MS) {
        if (!cancelled) {
          setTimedOut(true)
          setLoading(false)
        }
        return
      }

      window.setTimeout(() => {
        void poll()
      }, POLL_INTERVAL_MS)
    }

    void poll()

    return () => {
      cancelled = true
    }
  }, [session, status])

  if (status === "loading" || loading) {
    return (
      <div className="flex items-center justify-center min-h-[60vh]">
        <Loader2 className="w-6 h-6 animate-spin text-slate-500" />
      </div>
    )
  }

  if (status === "unauthenticated" || !session?.backendAccessToken) {
    return (
      <main className="max-w-lg mx-auto px-4 py-20 text-center space-y-6">
        <h1 className="text-2xl font-bold text-white">Sign in to confirm billing status</h1>
        <p className="text-slate-400">
          We need your account session to verify your latest subscription state.
        </p>
        <Link
          href="/auth?callbackUrl=/billing/success"
          className="inline-flex bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors"
        >
          Sign in
        </Link>
      </main>
    )
  }

  const sub = current?.subscription

  return (
    <main className="max-w-lg mx-auto px-4 py-20 text-center space-y-6">
      <div className="flex justify-center">
        <div className="w-16 h-16 rounded-full bg-emerald-500/20 flex items-center justify-center">
          <CheckCircle2 className="w-8 h-8 text-emerald-400" />
        </div>
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-white flex items-center justify-center gap-2">
          <Sparkles className="w-5 h-5 text-amber-400" />
          You&apos;re all set!
        </h1>
        {sub && isSubscriptionActive(sub.status) ? (
          <p className="text-slate-400">
            Your{" "}
            <span className="text-white font-medium capitalize">{sub.plan}</span> plan is now{" "}
            <span className="text-emerald-400 font-medium">{sub.status}</span>. Start tailoring
            resumes right away.
          </p>
        ) : timedOut ? (
          <p className="text-amber-300">
            Checkout completed, but activation is still processing. This usually resolves within a
            minute after Stripe webhook delivery.
          </p>
        ) : (
          <p className="text-slate-400">
            Your subscription is confirmed. It may take a few moments to activate.
          </p>
        )}
      </div>

      <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
        <Link
          href="/session/new"
          className="bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors"
        >
          Start a new session
        </Link>
        <Link
          href="/billing"
          className="bg-slate-800 text-slate-200 font-medium text-sm px-6 py-2.5 rounded-xl hover:bg-slate-700 transition-colors border border-slate-700"
        >
          View billing
        </Link>
      </div>
    </main>
  )
}
