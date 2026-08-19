"use client"

import { ChevronDown, ChevronUp, FileText } from "lucide-react"
import { clsx } from "clsx"

interface Props {
  count: number | null
  fallbackLabel?: string
  collapsed: boolean
  onToggle: () => void
}

export function TailoredUsagePanel({
  count,
  fallbackLabel,
  collapsed,
  onToggle,
}: Props) {
  const label =
    count !== null
      ? `Used in ${count} tailored resume${count === 1 ? "" : "s"}`
      : (fallbackLabel ?? "Tailored resume usage unavailable")

  return (
    <>
      <aside
        className={clsx(
          "hidden lg:block bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-2xl overflow-hidden",
          "lg:sticky lg:top-20 lg:self-start",
        )}
      >
        <div className="p-5 space-y-3">
          <div className="flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-200">
            <FileText className="w-4 h-4 text-amber-700 dark:text-amber-400" />
            Tailored usage
          </div>
          <p className="text-sm text-slate-700 dark:text-slate-300">{label}</p>
          {count === null && (
            <p className="text-xs text-slate-600 dark:text-slate-400">
              Resume history tracking arrives in a later release. Your master profile is still
              used for every new tailoring session.
            </p>
          )}
        </div>
      </aside>

      <div className="lg:hidden fixed bottom-4 inset-x-4 z-30">
        <button
          type="button"
          onClick={onToggle}
          className="w-full flex items-center justify-between px-4 py-3 text-sm text-slate-800 dark:text-slate-200 bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-xl shadow-xl"
          aria-expanded={!collapsed}
        >
          <span className="flex items-center gap-2 min-w-0">
            <FileText className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0" />
            <span className="truncate">{label}</span>
          </span>
          {collapsed ? (
            <ChevronUp className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          )}
        </button>
      </div>

      {!collapsed && (
        <div className="lg:hidden fixed inset-0 z-20 bg-slate-50/60 dark:bg-slate-950/60" onClick={onToggle}>
          <div
            className="absolute bottom-0 inset-x-0 rounded-t-2xl border-t border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 p-5"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mx-auto mb-3 h-1.5 w-12 rounded-full bg-slate-200 dark:bg-slate-700" />
            <div className="space-y-3">
              <div className="flex items-center gap-2 text-sm font-medium text-slate-800 dark:text-slate-200">
                <FileText className="w-4 h-4 text-amber-700 dark:text-amber-400" />
                Tailored usage
              </div>
              <p className="text-sm text-slate-700 dark:text-slate-300">{label}</p>
              {count === null && (
                <p className="text-xs text-slate-600 dark:text-slate-400">
                  Resume history tracking arrives in a later release. Your master profile is still
                  used for every new tailoring session.
                </p>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
