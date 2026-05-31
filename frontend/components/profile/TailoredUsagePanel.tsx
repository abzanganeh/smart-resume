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
    <aside
      className={clsx(
        "bg-slate-900 border border-slate-700 rounded-2xl overflow-hidden",
        "lg:sticky lg:top-20 lg:self-start",
      )}
    >
      <button
        type="button"
        onClick={onToggle}
        className="lg:hidden w-full flex items-center justify-between px-4 py-3 text-sm text-slate-300 hover:bg-slate-800 transition-colors"
        aria-expanded={!collapsed}
      >
        <span className="flex items-center gap-2">
          <FileText className="w-4 h-4 text-amber-400" />
          {label}
        </span>
        {collapsed ? (
          <ChevronDown className="w-4 h-4 text-slate-500" />
        ) : (
          <ChevronUp className="w-4 h-4 text-slate-500" />
        )}
      </button>

      <div className={clsx("p-5 space-y-3", collapsed && "hidden lg:block")}>
        <div className="hidden lg:flex items-center gap-2 text-sm font-medium text-slate-200">
          <FileText className="w-4 h-4 text-amber-400" />
          Tailored usage
        </div>
        <p className="text-sm text-slate-300">{label}</p>
        {count === null && (
          <p className="text-xs text-slate-500">
            Resume history tracking arrives in a later release. Your master profile is still
            used for every new tailoring session.
          </p>
        )}
      </div>
    </aside>
  )
}
