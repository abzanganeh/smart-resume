"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useSession } from "next-auth/react"
import { getSubscriptionCurrent } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"

export function JobsNavItem() {
  const { data: session, status } = useSession()
  const token = session?.backendAccessToken
  const [subscribed, setSubscribed] = useState<boolean | null>(null)

  useEffect(() => {
    if (!token || status !== "authenticated") {
      setSubscribed(null)
      return
    }

    let cancelled = false
    ;(async () => {
      try {
        const data = await getSubscriptionCurrent(token)
        const sub = data.subscription
        if (!cancelled) {
          setSubscribed(!!sub && isSubscriptionActive(sub.status))
        }
      } catch {
        if (!cancelled) setSubscribed(false)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [token, status])

  if (status !== "authenticated" || subscribed === null) {
    return (
      <span className="px-3 py-1.5 rounded-lg text-slate-600 whitespace-nowrap text-sm">
        Search jobs
      </span>
    )
  }

  if (subscribed) {
    return (
      <Link
        href="/jobs"
        className="px-3 py-1.5 rounded-lg hover:bg-slate-800 hover:text-slate-200 transition-colors whitespace-nowrap"
      >
        Search jobs
      </Link>
    )
  }

  return (
    <Link
      href="/billing"
      className="px-3 py-1.5 rounded-lg hover:bg-slate-800 transition-colors whitespace-nowrap inline-flex items-center gap-1.5 text-amber-400/90 hover:text-amber-300"
      title="Subscribe to search jobs"
    >
      Search jobs
      <span className="text-[10px] font-bold bg-amber-400 text-slate-900 px-1.5 py-0.5 rounded-full">
        Upgrade
      </span>
    </Link>
  )
}
