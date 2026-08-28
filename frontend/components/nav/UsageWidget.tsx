"use client"

import Link from "next/link"
import { useEffect, useRef, useState } from "react"
import { useSession } from "next-auth/react"
import { Loader2, TrendingUp, Zap } from "lucide-react"
import { getSubscriptionCurrent, ApiError, type SubscriptionCurrentResponse } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"
import { CreditMeter } from "@/components/billing/CreditMeter"
import {
  isRefreshRateLimited,
  refreshBackendSession,
} from "@/lib/auth/refreshBackendSession"

const POLL_MS = 60_000

export function UsageWidget() {
  const { data: session, status, update } = useSession()
  const updateRef = useRef(update)
  useEffect(() => {
    updateRef.current = update
  }, [update])

  const tokenExpired = session?.error === "TokenExpired"
  const token = tokenExpired ? undefined : session?.backendAccessToken

  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const fetchedTokenRef = useRef<string | null>(null)
  const hasDataRef = useRef(false)

  useEffect(() => {
    if (!token || status !== "authenticated") {
      setCurrent(null)
      setLoading(false)
      fetchedTokenRef.current = null
      hasDataRef.current = false
      return
    }

    let cancelled = false

    const load = async (force = false) => {
      if (!force && fetchedTokenRef.current === token) return

      if (!hasDataRef.current) setLoading(true)
      try {
        const data = await getSubscriptionCurrent(token)
        if (cancelled) return
        fetchedTokenRef.current = token
        hasDataRef.current = true
        setCurrent(data)
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 429) {
          return
        }
        if (!hasDataRef.current) setCurrent(null)
        if (e instanceof ApiError && e.status === 401 && !isRefreshRateLimited()) {
          void refreshBackendSession(updateRef.current)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }

    void load(false)
    const id = window.setInterval(() => void load(true), POLL_MS)
    return () => {
      cancelled = true
      window.clearInterval(id)
    }
  }, [token, status])

  if (status === "loading" || status === "unauthenticated" || !token) return null
  if (loading && !current) {
    return <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-600 dark:text-slate-400" />
  }
  if (!current) return null

  const sub = current.subscription
  const isSubscribed = !!sub && isSubscriptionActive(sub.status)

  if (isSubscribed && sub) {
    const tierLabel =
      sub.plan_display_name ?? sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1)
    const resumeCap = current.credit_cap ?? sub.resumes_limit
    const resumeUsed = current.credits_used ?? sub.resumes_used

    return (
      <Link
        href="/billing"
        className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 min-w-[10rem]"
        title={`${tierLabel}: ${resumeUsed}/${resumeCap} resumes this period`}
      >
        <TrendingUp className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400 shrink-0" />
        <span className="hidden sm:inline text-amber-700 dark:text-amber-400">{tierLabel}</span>
        <CreditMeter
          used={resumeUsed}
          cap={resumeCap}
          label="Resumes"
          compact
          className="hidden sm:block flex-1 min-w-[5rem] max-w-[8rem]"
        />
      </Link>
    )
  }

  const credits =
    current.spendable_credit_balance ??
    current.credit_balance ??
    session?.backendUser?.credit_balance ??
    0
  const locked = current.credits_locked_until_verification
  const creditCap = current.credit_cap ?? credits
  const creditsUsed = current.credits_used ?? Math.max(0, creditCap - credits)

  return (
    <Link
      href={locked ? "/settings" : "/billing"}
      className="flex items-center gap-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:text-slate-900 dark:hover:text-white transition-colors bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 min-w-[10rem]"
      title={
        locked
          ? `${credits} signup credits — verify your email in Settings to use them.`
          : "Free plan — credits pay for tailoring, cover letters, and coaching."
      }
    >
      <Zap className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400 shrink-0" />
      <CreditMeter
        used={creditsUsed}
        cap={creditCap}
        label={locked ? "Verify email" : "Credits left"}
        compact
        className="flex-1 min-w-[5rem] max-w-[9rem]"
      />
      <span className="hidden lg:inline bg-amber-400 text-slate-900 text-[10px] font-bold px-1.5 py-0.5 rounded-full">
        Upgrade
      </span>
    </Link>
  )
}
