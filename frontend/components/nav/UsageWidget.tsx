"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useSession } from "next-auth/react"
import { Loader2, TrendingUp, Zap } from "lucide-react"
import { getSubscriptionCurrent, type SubscriptionCurrentResponse } from "@/lib/api"

const CACHE_TTL_MS = 30_000

let _cache: { data: SubscriptionCurrentResponse; fetchedAt: number } | null = null

function getCached(): SubscriptionCurrentResponse | null {
  if (!_cache) return null
  if (Date.now() - _cache.fetchedAt > CACHE_TTL_MS) return null
  return _cache.data
}

function setCache(data: SubscriptionCurrentResponse) {
  _cache = { data, fetchedAt: Date.now() }
}

export function UsageWidget() {
  const { data: session, status } = useSession()
  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(getCached)
  const [loading, setLoading] = useState(!getCached())
  const fetchedRef = useRef(false)

  useEffect(() => {
    const token = session?.backendAccessToken
    if (!token || fetchedRef.current) return

    const cached = getCached()
    if (cached) {
      setCurrent(cached)
      setLoading(false)
      return
    }

    fetchedRef.current = true
    getSubscriptionCurrent(token)
      .then((data) => {
        setCache(data)
        setCurrent(data)
      })
      .catch(() => {
        /* ignore — widget is non-critical */
      })
      .finally(() => setLoading(false))
  }, [session])

  if (status === "loading" || status === "unauthenticated") return null
  if (loading) {
    return <Loader2 className="w-3.5 h-3.5 animate-spin text-slate-500" />
  }
  if (!current) return null

  const sub = current.subscription
  const isSubscribed = !!sub && sub.status !== "expired" && sub.status !== "cancelled"

  if (isSubscribed) {
    const tierLabel =
      sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1)

    return (
      <Link
        href="/billing"
        className="flex items-center gap-1.5 text-xs font-medium text-slate-300 hover:text-white transition-colors bg-slate-800 hover:bg-slate-700 px-2.5 py-1.5 rounded-lg border border-slate-700"
        title={`${sub.resumes_used} / ${sub.resumes_limit} resumes this period`}
      >
        <TrendingUp className="w-3.5 h-3.5 text-amber-400 shrink-0" />
        <span className="hidden sm:inline text-amber-400">{tierLabel}</span>
        <span className="hidden sm:inline text-slate-500">&middot;</span>
        <span className="tabular-nums">
          {sub.resumes_used}&thinsp;/&thinsp;{sub.resumes_limit}
        </span>
      </Link>
    )
  }

  // Free user
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
