"use client"

import { useCallback, useEffect, useState } from "react"
import { AlertCircle, CheckCircle2, Loader2, Plus, X } from "lucide-react"
import {
  getJobPreferences,
  getJobTitleSuggestions,
  MAX_PREFERRED_JOB_TITLES,
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

function normalizeTitle(title: string): string {
  return title.trim().replace(/\s+/g, " ")
}

function titleKey(title: string): string {
  return normalizeTitle(title).toLowerCase()
}

export function JobTitlePicker({
  accessToken,
  onComplete,
  submitLabel = "Continue to job search",
  className,
}: JobTitlePickerProps) {
  const [suggestions, setSuggestions] = useState<JobTitleSuggestion[]>([])
  const [heldTitles, setHeldTitles] = useState<string[]>([])
  const [selectedTitles, setSelectedTitles] = useState<string[]>([])
  const [customDraft, setCustomDraft] = useState("")
  const [titleLimit, setTitleLimit] = useState(MAX_PREFERRED_JOB_TITLES)
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const atMax = selectedTitles.length >= titleLimit

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const [res, prefs] = await Promise.all([
        getJobTitleSuggestions(accessToken),
        getJobPreferences(accessToken).catch(() => null),
      ])
      setSuggestions(res.suggestions)
      setHeldTitles(res.held_titles)
      const maxTitles = prefs?.max_preferred_titles ?? MAX_PREFERRED_JOB_TITLES
      setTitleLimit(maxTitles)

      const saved = prefs?.preferred_titles?.filter(Boolean) ?? []
      if (saved.length > 0) {
        setSelectedTitles(saved.slice(0, maxTitles))
      } else if (res.suggestions.length > 0) {
        setSelectedTitles([res.suggestions[0].title])
      } else {
        setSelectedTitles([])
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Could not load job title suggestions.")
    } finally {
      setLoading(false)
    }
  }, [accessToken])

  useEffect(() => {
    void load()
  }, [load])

  function isSelected(title: string): boolean {
    const key = titleKey(title)
    return selectedTitles.some((row) => titleKey(row) === key)
  }

  function addTitle(title: string) {
    const normalized = normalizeTitle(title)
    if (!normalized) return
    const key = titleKey(normalized)
    if (selectedTitles.some((row) => titleKey(row) === key)) {
      setError("That title is already in your list.")
      return
    }
    if (selectedTitles.length >= titleLimit) {
      setError(`You can save up to ${titleLimit} titles. Remove one to add another.`)
      return
    }
    setError(null)
    setSelectedTitles((prev) => [...prev, normalized])
    setCustomDraft("")
  }

  function removeTitle(title: string) {
    const key = titleKey(title)
    setSelectedTitles((prev) => prev.filter((row) => titleKey(row) !== key))
    setError(null)
  }

  function toggleSuggestion(title: string) {
    if (isSelected(title)) {
      removeTitle(title)
    } else {
      addTitle(title)
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (selectedTitles.length < MIN_PREFERRED_JOB_TITLES) {
      setError(`Select at least ${MIN_PREFERRED_JOB_TITLES} title to continue.`)
      return
    }
    setSaving(true)
    setError(null)
    try {
      await savePreferredJobTitles(accessToken, selectedTitles)
      await onComplete(selectedTitles)
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
          (up to {titleLimit}) — remove suggestions you do not want and add your own anytime.
        </p>
        {heldTitles.length > 0 && (
          <p className="text-xs text-slate-500 dark:text-slate-500">
            Includes titles from your experience: {heldTitles.slice(0, 3).join(", ")}
            {heldTitles.length > 3 ? "…" : ""}
          </p>
        )}
      </div>

      {selectedTitles.length > 0 && (
        <div className="space-y-2" data-testid="job-title-selected">
          <p className="text-xs font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-400">
            Your target roles ({selectedTitles.length}/{titleLimit})
          </p>
          <div className="flex flex-wrap gap-2">
            {selectedTitles.map((title) => (
              <span
                key={title}
                className="inline-flex items-center gap-1.5 rounded-full border border-amber-400/40 bg-amber-400/10 px-3 py-1 text-sm text-slate-800 dark:text-slate-100"
              >
                {title}
                <button
                  type="button"
                  onClick={() => removeTitle(title)}
                  className="rounded-full p-0.5 hover:bg-amber-400/30"
                  aria-label={`Remove ${title}`}
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="flex flex-col sm:flex-row gap-2">
        <input
          type="text"
          value={customDraft}
          onChange={(e) => setCustomDraft(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault()
              addTitle(customDraft)
            }
          }}
          placeholder="Add your own job title"
          disabled={atMax}
          maxLength={200}
          data-testid="job-title-custom-input"
          className="flex-1 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-3 py-2 text-sm text-slate-900 dark:text-slate-100 disabled:opacity-50"
        />
        <button
          type="button"
          onClick={() => addTitle(customDraft)}
          disabled={atMax || !customDraft.trim()}
          data-testid="job-title-custom-add"
          className="inline-flex items-center justify-center gap-1.5 px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-600 text-sm font-medium text-slate-700 dark:text-slate-200 hover:border-amber-400/60 disabled:opacity-40"
        >
          <Plus className="w-4 h-4" />
          Add title
        </button>
      </div>

      <div className="space-y-3 max-h-[28rem] overflow-y-auto pr-1" data-testid="job-title-suggestions">
        {suggestions.map((row) => {
          const selected = isSelected(row.title)
          return (
            <button
              key={row.title}
              type="button"
              onClick={() => toggleSuggestion(row.title)}
              disabled={!selected && atMax}
              data-testid={`job-title-option-${row.title}`}
              className={clsx(
                "w-full text-left rounded-xl border p-4 transition-colors disabled:opacity-50",
                selected
                  ? "border-amber-400 bg-amber-400/10 ring-1 ring-amber-400/40"
                  : "border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-900/60 hover:border-amber-400/50",
              )}
            >
              <div className="flex items-start justify-between gap-3">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {row.title}
                </h3>
                {selected ? (
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
        {selectedTitles.length} selected · minimum {MIN_PREFERRED_JOB_TITLES} · maximum{" "}
        {titleLimit}
      </p>

      {error && (
        <div className="flex items-start gap-2 text-red-700 dark:text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <button
        type="submit"
        disabled={saving || selectedTitles.length < MIN_PREFERRED_JOB_TITLES}
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
