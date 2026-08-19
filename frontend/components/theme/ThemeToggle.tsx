"use client"

import { Moon, Sun } from "lucide-react"
import { useTheme } from "@/components/theme/ThemeProvider"
import { clsx } from "clsx"

type ThemeToggleProps = {
  className?: string
  showLabel?: boolean
}

/** Toggles between light and dark (uses resolved appearance, not system cycle). */
export function ThemeToggle({ className, showLabel = true }: ThemeToggleProps) {
  const { resolvedTheme, setTheme } = useTheme()

  function toggle() {
    setTheme(resolvedTheme === "dark" ? "light" : "dark")
  }

  const label = resolvedTheme === "dark" ? "Dark" : "Light"

  return (
    <button
      type="button"
      onClick={toggle}
      className={clsx(
        "inline-flex items-center gap-2 rounded-lg border border-slate-300 bg-white/80 px-2.5 py-1.5 text-slate-700 hover:bg-slate-100 transition-colors",
        "dark:border-slate-700 dark:bg-slate-900/80 dark:text-slate-200 dark:hover:bg-slate-800",
        className,
      )}
      aria-label={`Theme: ${label}. Click to change.`}
      title={`Theme: ${label}`}
    >
      {resolvedTheme === "dark" ? (
        <Moon className="h-4 w-4 shrink-0" aria-hidden />
      ) : (
        <Sun className="h-4 w-4 shrink-0" aria-hidden />
      )}
      <span className="text-xs font-medium">{label}</span>
    </button>
  )
}
