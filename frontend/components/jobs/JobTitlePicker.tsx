"use client"

import { useCallback, useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, Loader2, Search } from "lucide-react"
import {
  getJobTitleSuggestions,
  MIN_PREFERRED_JOB_TITLES,
  savePreferredJobTitles,
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
  const [suggestions, setSuggestions] = useState<string[]>([])
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
      for (const title of res.suggestions.slice(0, MIN_PREFERRED_JOB_TITLES)) {
        preselect.add(title)
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
          Based on your master resume, we suggest roles to search for. Pick at least{" "}
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

      <div className="flex flex-wrap gap-2 justify-center" data-testid="job-title-suggestions">
        {suggestions.map((title) => {
          const isSelected = selected.has(title)
          return (
            <button
              key={title}
              type="button"
              onClick={() => toggle(title)}
              data-testid={`job-title-option-${title}`}
              className={clsx(
                "inline-flex items-center gap-1.5 px-3 py-2 rounded-full text-sm border transition-colors",
                isSelected
                  ? "bg-amber-400/20 border-amber-400 text-amber-900 dark:text-amber-200"
                  : "bg-slate-50 dark:bg-slate-900 border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:border-amber-400/60",
              )}
            >
              {isSelected ? (
                <CheckCircle2 className="w-3.5 h-3.5 shrink-0" />
              ) : (
                <Search className="w-3.5 h-3.5 shrink-0 opacity-50" />
              )}
              {title}
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
