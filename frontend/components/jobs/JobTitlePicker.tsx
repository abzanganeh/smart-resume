"use client"

import { useCallback, useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, Loader2 } from "lucide-react"
import {
  getJobTitleSuggestions,
  MIN_PREFERRED_JOB_TITLES,
  savePreferredJobTitles,
  titleFitBar,
  titleFitLabel,
  type JobTitleSuggestion,
} from "@/lib/jobs"
import { clsx } from "clsx"

interface JobTitlePickerProps {
  accessToken: string
  onComplete: (titles: string[]) => void | Promise<void>
  submitLabel?: string
  className?: string
}

export function JobTitlePicker({
  accessToken,
  onComplete,
  submitLabel = "Continue to job search",
  className,
}: JobTitlePickerProps) {
  const [suggestions, setSuggestions] = useState<JobTitleSuggestion[]>([])
  const [heldTitles, setHeldTitles] = useState<string[]>([])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const res = await getJobTitleSuggestions(accessToken)
      setSuggestions(res.suggestions)
      setHeldTitles(res.held_titles)
      const preselect = new Set<string>()
      for (const row of res.suggestions.slice(0, MIN_PREFERRED_JOB_TITLES)) {
        preselect.add(row.title)
      }
      setSelected(preselect)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load job title suggestions.")
    } finally {
      setLoading(false)
    }
  }, [accessToken])

  useEffect(() => {
    void load()
  }, [load])

  function toggle(title: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(title)) {
        next.delete(title)
      } else {
        next.add(title)
      }
      return next
    })
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (selected.size < MIN_PREFERRED_JOB_TITLES) {
      setError(`Select at least ${MIN_PREFERRED_JOB_TITLES} titles to continue.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      const titles = Array.from(selected)
      await savePreferredJobTitles(accessToken, titles)
      await onComplete(titles)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save your selections.")
    } finally {
      setSaving(false)
    }
  }

  if (loading) {
    return (
      <div className={clsx("flex items-center justify-center py-12 text-slate-600 dark:text-slate-400", className)}>
        <Loader2 className="w-5 h-5 animate-spin mr-2" />
        Analyzing your resume for job titles…
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className={clsx("space-y-5", className)}>
      <div className="text-center space-y-2">
        <p className="text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
          Based on your master resume, we ranked roles by fit. Pick at least{" "}
          <strong className="text-slate-900 dark:text-slate-200">{MIN_PREFERRED_JOB_TITLES}</strong>{" "}
          — you can refine these anytime on the Jobs page.
        </p>
        {heldTitles.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-500">
            Includes titles from your experience: {heldTitles.slice(0, 3).join(", ")}
            {heldTitles.length > 3 ? "…" : ""}
          </p>
        )}
      </div>

      <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1" data-testid="job-title-suggestions">
        {suggestions.map((row) => {
          const isSelected = selected.has(row.title)
          return (
            <button
              key={row.title}
              type="button"
              onClick={() => toggle(row.title)}
              data-testid={`job-title-option-${row.title}`}
              className={clsx(
                "w-full text-left rounded-xl border p-4 transition-colors",
                isSelected
                  ? "border-amber-400 bg-amber-400/10 ring-1 ring-amber-400/40"
                  : "border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-900/60 hover:border-amber-400/50",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {row.title}
                </h3>
                {isSelected ? (
                  <CheckCircle2 className="w-4 h-4 shrink-0 text-amber-600 dark:text-amber-400" />
                ) : null}
              </div>

              <p
                className="mt-2 font-mono text-[11px] leading-none tracking-tight text-emerald-700 dark:text-emerald-400"
                aria-label={titleFitLabel(row.fit_score)}
              >
                {titleFitBar(row.fit_score)}{" "}
                <span className="text-slate-600 dark:text-slate-400">{titleFitLabel(row.fit_score)}</span>
              </p>

              {row.strengths.length > 0 && (
                <ul className="mt-3 space-y-1">
                  {row.strengths.map((line) => (
                    <li
                      key={line}
                      className="text-xs text-emerald-800 dark:text-emerald-300/90 flex gap-2"
                    >
                      <span className="shrink-0">+</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              )}

              {row.weaknesses.length > 0 && (
                <ul className="mt-2 space-y-1">
                  {row.weaknesses.map((line) => (
                    <li
                      key={line}
                      className="text-xs text-amber-800 dark:text-amber-300/90 flex gap-2"
                    >
                      <span className="shrink-0">−</span>
                      <span>{line}</span>
                    </li>
                  ))}
                </ul>
              )}
            </button>
          )
        })}
      </div>

      <p className="text-center text-xs text-slate-500 dark:text-slate-500">
        {selected.size} selected · minimum {MIN_PREFERRED_JOB_TITLES}
      </p>

      {error && (
        <div className="flex items-start gap-2 text-red-700 dark:text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={saving || selected.size < MIN_PREFERRED_JOB_TITLES}
        data-testid="job-title-picker-submit"
        className="w-full inline-flex items-center justify-center gap-2 px-6 py-3 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 disabled:opacity-40"
      >
        {saving ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Saving…
          </>
        ) : (
          submitLabel
        )}
      </button>
    </form>
  )
}
