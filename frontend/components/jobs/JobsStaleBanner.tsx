"use client"

import { AlertTriangle } from "lucide-react"
import { staleBannerMessage } from "@/lib/jobs"

interface Props {
  resultsMayBeStale: boolean
  message?: string | null
}

export function JobsStaleBanner({ resultsMayBeStale, message }: Props) {
  const text = staleBannerMessage(resultsMayBeStale, message)
  if (!text) return null

  return (
    <div
      role="status"
      data-testid="jobs-stale-banner"
      className="flex items-start gap-2 bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/30 rounded-lg px-4 py-3 mb-6 text-amber-800 dark:text-amber-200 text-sm"
    >
      <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-700 dark:text-amber-400" aria-hidden />
      <span>{text}</span>
    </div>
  )
}
