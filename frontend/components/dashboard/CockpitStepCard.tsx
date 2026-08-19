"use client"

import Link from "next/link"
import { clsx } from "clsx"
import type { LucideIcon } from "lucide-react"

interface CockpitStepCardProps {
  step: number
  title: string
  description: string
  ready: boolean
  locked?: boolean
  icon: LucideIcon
  primaryHref?: string
  primaryLabel?: string
  secondaryHref?: string
  secondaryLabel?: string
}

export function CockpitStepCard({
  step,
  title,
  description,
  ready,
  locked = false,
  icon: Icon,
  primaryHref,
  primaryLabel,
  secondaryHref,
  secondaryLabel,
}: CockpitStepCardProps) {
  return (
    <div
      className={clsx(
        "rounded-2xl border p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4",
        ready
          ? "border-emerald-400/20 bg-emerald-400/5"
          : locked
            ? "border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/40 opacity-70"
            : "border-amber-400/20 bg-amber-500/5 dark:bg-amber-400/5",
      )}
    >
      <div className="flex items-start gap-3 flex-1 min-w-0">
        <div
          className={clsx(
            "w-9 h-9 rounded-full flex items-center justify-center shrink-0 text-sm font-bold",
            ready
              ? "bg-emerald-500/20 text-emerald-800 dark:text-emerald-300"
              : locked
                ? "bg-slate-200 dark:bg-slate-800 text-slate-500"
                : "bg-amber-400/25 text-amber-900 dark:text-amber-200",
          )}
        >
          {ready ? "✓" : step}
        </div>
        <div className="space-y-1 min-w-0">
          <p className="text-slate-900 dark:text-white font-semibold text-lg flex items-center gap-2">
            <Icon className="w-5 h-5 shrink-0 text-amber-700 dark:text-amber-400" />
            {title}
          </p>
          <p className="text-slate-600 dark:text-slate-400 text-sm">{description}</p>
        </div>
      </div>
      {!locked && primaryHref && primaryLabel && (
        <div className="flex flex-col sm:flex-row gap-2 shrink-0 w-full sm:w-auto">
          <Link
            href={primaryHref}
            className="px-5 py-2.5 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors text-sm text-center"
          >
            {primaryLabel}
          </Link>
          {secondaryHref && secondaryLabel && (
            <Link
              href={secondaryHref}
              className="px-5 py-2.5 border border-slate-400 dark:border-slate-600 hover:border-slate-500 text-slate-700 dark:text-slate-200 rounded-xl transition-colors text-sm text-center"
            >
              {secondaryLabel}
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
