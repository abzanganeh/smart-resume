"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useSession } from "next-auth/react"
import { Loader2, TrendingUp, Zap } from "lucide-react"
import { getSubscriptionCurrent, ApiError, type SubscriptionCurrentResponse } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"
import { refreshBackendSession } from "@/lib/auth/refreshBackendSession"

const POLL_MS = 60_000

export function UsageWidget() {
  const { data: session, status, update } = useSession()
  const updateRef = useRef(update)
  updateRef.current = update

  const tokenExpired = session?.error === "TokenExpired"
  const token = tokenExpired ? undefined : session?.backendAccessToken

  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(null)
  const [loading, setLoading] = useState(false)
  const fetchedTokenRef = useRef<string | null>(null)

  useEffect(() => {
    if (!token || status !== "authenticated") {
      setCurrent(null)
      setLoading(false)
      fetchedTokenRef.current = null
      return
    }

    let cancelled = false

    const load = async (force = false) => {
      if (!force && fetchedTokenRef.current === token) return

      setLoading(true)
      try {
        const data = await getSubscriptionCurrent(token)
        if (cancelled) return
        fetchedTokenRef.current = token
        setCurrent(data)
      } catch (e) {
        if (cancelled) return
        if (e instanceof ApiError && e.status === 429) {
          // Shared client cache handles cooldown — do not retry in a loop.
          return
        }
        setCurrent(null)
        if (e instanceof ApiError && e.status === 401) {
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
    return <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
  }
  if (!current) return null

  const sub = current.subscription
  const isSubscribed = !!sub && isSubscriptionActive(sub.status)

  if (isSubscribed) {
    const tierLabel = sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1)

    return (
      <Link
        href="/billing"
        className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white transition-colors bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-700"
        title={`${tierLabel}: ${sub.resumes_used}/${sub.resumes_limit} resumes, ${sub.searches_used}/${sub.searches_limit} searches this period`}
      >
        <TrendingUp className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        <span className="hidden sm:inline text-amber-400">{tierLabel}</span>
        <span className="hidden sm:inline text-slate-500">&middot;</span>
        <span className="tabular-nums" aria-label="resume usage">
          {sub.resumes_used}&thinsp;/&thinsp;{sub.resumes_limit}
        </span>
        <span className="hidden md:inline text-slate-500">&middot;</span>
        <span className="hidden md:inline tabular-nums" aria-label="search usage">
          {sub.searches_used}&thinsp;/&thinsp;{sub.searches_limit}
        </span>
      </Link>
    )
  }

  const credits = current.credit_balance
  return (
    <Link
      href="/billing"
      className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white transition-colors bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-700"
      title="Upgrade to a plan for unlimited access"
    >
      <Zap className="w-3.5 h-3.5 text-amber-400 shrink-0" />
      <span className="tabular-nums">{credits}</span>
      <span className="hidden sm:inline text-slate-400">
        {credits === 1 ? "credit" : "credits"} left
      </span>
      <span className="hidden sm:inline bg-amber-400 text-slate-900 text-[10px] font-bold px-1.5 py-0.5 rounded-full ml-0.5">
        Upgrade
      </span>
    </Link>
  )
}
