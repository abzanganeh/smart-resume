"use client"

import { useEffect, useRef, useState } from "react"
import Link from "next/link"
import { useSession } from "next-auth/react"
import { Loader2, TrendingUp, Zap } from "lucide-react"
import { getSubscriptionCurrent, type SubscriptionCurrentResponse } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"

const CACHE_TTL_MS = 30_000

let _cache: { token: string; data: SubscriptionCurrentResponse; fetchedAt: number } | null = null

function getCached(token: string): SubscriptionCurrentResponse | null {
  if (!_cache) return null
  if (_cache.token !== token) return null
  if (Date.now() - _cache.fetchedAt > CACHE_TTL_MS) return null
  return _cache.data
}

function setCache(token: string, data: SubscriptionCurrentResponse) {
  _cache = { token, data, fetchedAt: Date.now() }
}

export function UsageWidget() {
  const { data: session, status, update } = useSession()
  // Treat an expired backend token the same as no token — stop polling until re-auth.
  const tokenExpired = session?.error === "TokenExpired"
  const token = tokenExpired ? undefined : session?.backendAccessToken
  const [current, setCurrent] = useState<SubscriptionCurrentResponse | null>(
    token ? getCached(token) : null,
  )
  const [loading, setLoading] = useState(Boolean(token && !getCached(token)))
  const intervalRef = useRef<number | null>(null)

  useEffect(() => {
    if (!token) {
      const timeout = window.setTimeout(() => {
        setCurrent(null)
        setLoading(false)
      }, 0)
      return () => {
        window.clearTimeout(timeout)
      }
    }

    if (status !== "authenticated") {
      return
    }

    let cancelled = false

    const refresh = async (force = false) => {
      const cached = getCached(token)
      if (!force && cached) {
        setCurrent(cached)
        setLoading(false)
        return
      }

      setLoading(true)
      try {
        const data = await getSubscriptionCurrent(token)
        if (cancelled) return
        setCache(token, data)
        setCurrent(data)
      } catch {
        if (!cancelled) {
          setCurrent(null)
          // Stop polling and force a session re-check so all components learn
          // about the token expiry (session.error = "TokenExpired") at once.
          if (intervalRef.current !== null) {
            window.clearInterval(intervalRef.current)
            intervalRef.current = null
          }
          void update()
        }
      } finally {
        if (!cancelled) {
          setLoading(false)
        }
      }
    }

    void refresh(false)

    intervalRef.current = window.setInterval(() => {
      void refresh(true)
    }, CACHE_TTL_MS)

    return () => {
      cancelled = true
      if (intervalRef.current) {
        window.clearInterval(intervalRef.current)
      }
    }
  }, [token, status])

  if (status === "loading" || status === "unauthenticated") return null
  if (loading) {
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
