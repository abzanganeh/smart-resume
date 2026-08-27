"use client"

import Link from "next/link"
import { clsx } from "clsx"
import type { LucideIcon } from "lucide-react"

/**
 * A single step in the dashboard progress stack.
 *
 * States:
 *  - **locked**: prereq not met; grey, disabled, no CTAs.
 *  - **active/amber**: current focus; expanded card with description + CTAs.
 *  - **ready + compact** (default when `ready`): slim one-line row with two
 *    CTAs (primary + secondary), because the step is done and the user
 *    doesn't need the full explanation any more.
 *  - **ready + expanded** (opt-in via `expandedWhenReady`): keep the full
 *    card even after completion, useful for steps like "Job roles ready"
 *    that need to show the current picks.
 */
export interface DashboardStepCardProps {
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
  /**
   * On a prerequisite-locked step, optional escape hatch so power users can
   * jump ahead without implying the recommended path is complete.
   */
  skipHref?: string
  skipLabel?: string
  /** When true and `ready`, render the full-height card. Default: slim. */
  expandedWhenReady?: boolean
  /**
   * Distinguish an intentionally-unavailable step (e.g. a future feature)
   * from a prerequisite-locked step by rendering a dashed border and a
   * "Coming soon" chip.  Has no effect unless `locked` is also true.
   */
  comingSoon?: boolean
  /** Optional testid for e2e / component tests. */
  testId?: string
}

export function DashboardStepCard({
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
  skipHref,
  skipLabel,
  expandedWhenReady = false,
  comingSoon = false,
  testId,
}: DashboardStepCardProps) {
  const isExternal = (href: string) => /^https?:\/\//i.test(href)
  const slim = ready && !expandedWhenReady
  const border = ready
    ? "border-emerald-400/30 bg-emerald-400/5"
    : locked && comingSoon
      ? "border-dashed border-slate-300 dark:border-slate-700 bg-slate-50/60 dark:bg-slate-900/30 opacity-80"
      : locked
        ? "border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-900/40 opacity-70"
        : "border-amber-400/30 bg-amber-500/5 dark:bg-amber-400/5"

  const badge = (
    <div
      className={clsx(
        "rounded-full flex items-center justify-center shrink-0 font-bold",
        slim ? "w-7 h-7 text-xs" : "w-9 h-9 text-sm",
        ready
          ? "bg-emerald-500/20 text-emerald-800 dark:text-emerald-300"
          : locked
            ? "bg-slate-200 dark:bg-slate-800 text-slate-500"
            : "bg-amber-400/25 text-amber-900 dark:text-amber-200",
      )}
      aria-hidden
    >
      {ready ? "✓" : step}
    </div>
  )

  if (slim) {
    return (
      <div
        data-testid={testId}
        data-state="ready-slim"
        className={clsx(
          "rounded-2xl border px-5 py-3 flex flex-col sm:flex-row sm:items-center gap-3",
          border,
        )}
      >
        <div className="flex items-center gap-3 flex-1 min-w-0">
          {badge}
          <Icon className="w-4 h-4 shrink-0 text-emerald-700 dark:text-emerald-400" />
          <p className="text-slate-900 dark:text-white font-medium text-sm truncate">
            {title}
          </p>
        </div>
        {primaryHref && primaryLabel && (
          <div className="flex flex-row gap-2 shrink-0 w-full sm:w-auto">
            <Link
              href={primaryHref}
              target={isExternal(primaryHref) ? "_blank" : undefined}
              rel={isExternal(primaryHref) ? "noopener noreferrer" : undefined}
              className="flex-1 sm:flex-none min-h-[40px] px-4 py-2.5 sm:py-1.5 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-lg transition-colors text-sm sm:text-xs text-center inline-flex items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
            >
              {primaryLabel}
            </Link>
            {secondaryHref && secondaryLabel && (
              <Link
                href={secondaryHref}
                className="flex-1 sm:flex-none min-h-[40px] px-4 py-2.5 sm:py-1.5 border border-slate-400 dark:border-slate-600 hover:border-slate-500 text-slate-700 dark:text-slate-200 rounded-lg transition-colors text-sm sm:text-xs text-center inline-flex items-center justify-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
              >
                {secondaryLabel}
              </Link>
            )}
          </div>
        )}
      </div>
    )
  }

  return (
    <div
      data-testid={testId}
      data-state={ready ? "ready-expanded" : locked ? "locked" : "active"}
      className={clsx(
        "rounded-2xl border p-6 flex flex-col sm:flex-row items-start sm:items-center gap-4",
        border,
      )}
    >
      <div className="flex items-start gap-3 flex-1 min-w-0">
        {badge}
        <div className="space-y-1 min-w-0">
          <p className="text-slate-900 dark:text-white font-semibold text-lg flex items-center gap-2 flex-wrap">
            <Icon
              className={clsx(
                "w-5 h-5 shrink-0",
                ready
                  ? "text-emerald-700 dark:text-emerald-400"
                  : locked
                    ? "text-slate-500 dark:text-slate-500"
                    : "text-amber-700 dark:text-amber-400",
              )}
            />
            {title}
            {locked && comingSoon && (
              <span className="text-[10px] font-semibold uppercase tracking-wide bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300 px-2 py-0.5 rounded-full">
                Coming soon
              </span>
            )}
          </p>
          <p className="text-slate-600 dark:text-slate-400 text-sm">{description}</p>
          {locked && skipHref && skipLabel && (
            <Link
              href={skipHref}
              target={isExternal(skipHref) ? "_blank" : undefined}
              rel={isExternal(skipHref) ? "noopener noreferrer" : undefined}
              className="inline-flex mt-2 text-sm font-medium text-amber-800 dark:text-amber-300 hover:underline"
            >
              {skipLabel}
            </Link>
          )}
        </div>
      </div>
      {!locked && primaryHref && primaryLabel && (
        <div className="flex flex-col sm:flex-row gap-2 shrink-0 w-full sm:w-auto">
          <Link
            href={primaryHref}
            target={isExternal(primaryHref) ? "_blank" : undefined}
            rel={isExternal(primaryHref) ? "noopener noreferrer" : undefined}
            className="px-5 py-2.5 bg-amber-400 hover:bg-amber-300 text-slate-900 font-semibold rounded-xl transition-colors text-sm text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-amber-500 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
          >
            {primaryLabel}
          </Link>
          {secondaryHref && secondaryLabel && (
            <Link
              href={secondaryHref}
              className="px-5 py-2.5 border border-slate-400 dark:border-slate-600 hover:border-slate-500 text-slate-700 dark:text-slate-200 rounded-xl transition-colors text-sm text-center focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-slate-400 focus-visible:ring-offset-2 dark:focus-visible:ring-offset-slate-900"
            >
              {secondaryLabel}
            </Link>
          )}
        </div>
      )}
    </div>
  )
}
