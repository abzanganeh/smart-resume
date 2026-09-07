"use client"

import { useEffect, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Bookmark,
  BookmarkCheck,
  Building2,
  ClipboardList,
  ExternalLink,
  Loader2,
  MapPin,
  Sparkles,
  Target,
} from "lucide-react"
import { clsx } from "clsx"
import {
  fitJob,
  getJobFit,
  formatMatchScore,
  formatPostedDate,
  formatSalaryRange,
  isJobNew,
  shouldBlurJobCard,
  type JobResult,
} from "@/lib/jobs"
import {
  formatDuplicateApplicationPrompt,
  formatTrackerLimitError,
  trackApplicationWithDuplicatePrompt,
} from "@/lib/trackApplicationFlow"
import { TrackerApiError } from "@/lib/tracker"
import { userFacingError } from "@/lib/userFacingError"
import type { FitAnalysisOutput } from "@/lib/api"

interface Props {
  job: JobResult
  index: number
  isSubscribed: boolean
  accessToken: string
  saved: boolean
  onSaveToggle: (jobId: string, saved: boolean) => Promise<void>
}

const FIT_LABEL_COLOR: Record<string, string> = {
  strong: "text-emerald-700 dark:text-emerald-400",
  good: "text-sky-700 dark:text-sky-400",
  partial: "text-amber-700 dark:text-amber-400",
  weak: "text-red-700 dark:text-red-400",
}

export function JobCard({
  job,
  index,
  isSubscribed,
  accessToken,
  saved,
  onSaveToggle,
}: Props) {
  const router = useRouter()
  const [fitResult, setFitResult] = useState<FitAnalysisOutput | null>(null)
  const [fitAnalysisId, setFitAnalysisId] = useState<string | null>(null)
  const [fitExpanded, setFitExpanded] = useState(false)
  const [fitLoading, setFitLoading] = useState(false)
  const [fitHydrating, setFitHydrating] = useState(false)
  const [fitError, setFitError] = useState<string | null>(null)
  const [saveLoading, setSaveLoading] = useState(false)
  const [trackLoading, setTrackLoading] = useState(false)
  const [trackError, setTrackError] = useState<string | null>(null)

  const blurred = shouldBlurJobCard(index, isSubscribed)
  const salary = formatSalaryRange(job)
  const showNewBadge = isJobNew(job)
  const matchScoreLabel = formatMatchScore(job.score)
  const hasFit = fitResult !== null

  useEffect(() => {
    if (!accessToken || blurred) return
    let cancelled = false
    setFitHydrating(true)
    void getJobFit(accessToken, job.id)
      .then((res) => {
        if (cancelled || !res) return
        setFitResult(res.result)
        setFitAnalysisId(res.analysis_id)
      })
      .catch(() => {
        // Non-fatal — user can still run Check Fit once.
      })
      .finally(() => {
        if (!cancelled) setFitHydrating(false)
      })
    return () => {
      cancelled = true
    }
  }, [accessToken, blurred, job.id])

  const handleCheckFit = async () => {
    if (blurred || fitLoading || fitHydrating) return
    if (hasFit) {
      setFitExpanded(true)
      return
    }
    setFitLoading(true)
    setFitError(null)
    setFitExpanded(false)
    try {
      const res = await fitJob(accessToken, job.id)
      setFitResult(res.result)
      setFitAnalysisId(res.analysis_id)
      setFitExpanded(true)
    } catch (e) {
      setFitError(userFacingError(e).message)
    } finally {
      setFitLoading(false)
    }
  }

  const handleSave = async () => {
    if (blurred || saveLoading) return
    setSaveLoading(true)
    try {
      await onSaveToggle(job.id, !saved)
    } finally {
      setSaveLoading(false)
    }
  }

  const handleTrackApplication = async () => {
    if (blurred || trackLoading) return
    setTrackLoading(true)
    setTrackError(null)
    try {
      const app = await trackApplicationWithDuplicatePrompt(
        accessToken,
        {
          jd_title: job.title,
          jd_company: job.company,
          job_url: job.apply_url ?? undefined,
          status: "draft",
        },
        (err) =>
          window.confirm(
            `${formatDuplicateApplicationPrompt(err)}\n\nAdd this application anyway?`,
          ),
      )
      router.push(`/tracker/${app.id}`)
    } catch (e) {
      if (e instanceof TrackerApiError && e.code === "tracker_limit_reached") {
        setTrackError(formatTrackerLimitError(e))
      } else if (e instanceof TrackerApiError && e.code === "duplicate_application") {
        setTrackError(null)
      } else {
        setTrackError(userFacingError(e).message)
      }
    } finally {
      setTrackLoading(false)
    }
  }

  return (
    <article
      data-testid={`job-card-${job.id}`}
      className={clsx(
        "relative rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5",
        blurred && "overflow-hidden",
      )}
    >
      <div className={clsx("space-y-4", blurred && "blur-sm select-none pointer-events-none")}>
        <div className="flex gap-4">
          <div className="w-12 h-12 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 flex items-center justify-center shrink-0">
            <Building2 className="w-6 h-6 text-slate-600 dark:text-slate-400" aria-hidden />
          </div>
          <div className="flex-1 min-w-0">
            <h3 className="text-base font-semibold text-slate-900 dark:text-white truncate">{job.title}</h3>
            <p className="text-sm text-slate-600 dark:text-slate-400">{job.company}</p>
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 mt-1 text-xs text-slate-600 dark:text-slate-400">
              {job.location && (
                <span className="inline-flex items-center gap-1">
                  <MapPin className="w-3 h-3" />
                  {job.location}
                </span>
              )}
              {salary && <span>{salary}</span>}
              <span>{formatPostedDate(job.posted_date)}</span>
            </div>
            <div className="flex flex-wrap gap-1.5 mt-2">
              {matchScoreLabel && (
                <span
                  data-testid={`job-match-score-${job.id}`}
                  className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-amber-500/15 text-amber-800 dark:text-amber-300 border border-amber-500/30 inline-flex items-center gap-1"
                >
                  <Sparkles className="w-3 h-3" aria-hidden />
                  {matchScoreLabel}
                </span>
              )}
              {showNewBadge && (
                <span
                  data-testid={`job-new-badge-${job.id}`}
                  className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-sky-500/15 text-sky-300 border border-sky-500/30"
                >
                  New
                </span>
              )}
              {job.remote && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-emerald-500/15 text-emerald-700 dark:text-emerald-300 border border-emerald-500/30">
                  Remote
                </span>
              )}
              {job.sources.map((source) => (
                <span
                  key={source}
                  className="px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wide bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700"
                >
                  {source === "hirebase"
                    ? "Hirebase"
                    : source === "apify"
                      ? "Apify"
                      : source === "corpus"
                        ? "Corpus"
                        : source}
                </span>
              ))}
              {job.employment_type && (
                <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-300 dark:border-slate-700 capitalize">
                  {job.employment_type.replace(/_/g, " ")}
                </span>
              )}
            </div>
          </div>
        </div>

        {fitResult && (
          <div
            data-testid={`job-fit-score-${job.id}`}
            className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-950/60 px-4 py-3 space-y-2"
          >
            <p className="text-sm text-slate-700 dark:text-slate-300">
              Fit score:{" "}
              <span className={clsx("font-semibold", FIT_LABEL_COLOR[fitResult.fit_label])}>
                {fitResult.overall_fit_score}/100 ({fitResult.fit_label})
              </span>
            </p>
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              {fitResult.recommendation}
            </p>
            {fitExpanded && (
              <div className="grid gap-3 sm:grid-cols-2 pt-1 border-t border-slate-200/80 dark:border-slate-800/80">
                {fitResult.key_strengths.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-500 mb-1">
                      Strengths
                    </p>
                    <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-1">
                      {fitResult.key_strengths.map((item) => (
                        <li key={item}>+ {item}</li>
                      ))}
                    </ul>
                  </div>
                )}
                {fitResult.key_gaps.length > 0 && (
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500 dark:text-slate-500 mb-1">
                      Gaps
                    </p>
                    <ul className="text-xs text-slate-600 dark:text-slate-400 space-y-1">
                      {fitResult.key_gaps.map((item) => (
                        <li key={item}>− {item}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>
            )}
            <div className="flex flex-wrap items-center gap-3 pt-1">
              <button
                type="button"
                onClick={() => setFitExpanded((open) => !open)}
                className="text-xs font-medium text-amber-800 dark:text-amber-300 hover:underline"
              >
                {fitExpanded ? "Hide details" : "Show strengths & gaps"}
              </button>
              {fitAnalysisId && (
                <Link
                  href={`/fit?analysis=${fitAnalysisId}`}
                  className="text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
                >
                  Full report →
                </Link>
              )}
            </div>
          </div>
        )}

        {fitError && <p className="text-xs text-red-700 dark:text-red-400">{fitError}</p>}
        {trackError && <p className="text-xs text-red-700 dark:text-red-400">{trackError}</p>}

        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            onClick={handleCheckFit}
            disabled={fitLoading || fitHydrating || blurred}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm hover:border-slate-600 disabled:opacity-40"
          >
            {fitLoading || fitHydrating ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Target className="w-4 h-4" />
            )}
            {hasFit ? "View fit" : "Check Fit"}
          </button>
          <Link
            href={`/session/new?jd_id=${job.id}&source=jobs`}
            data-testid={`tailor-resume-${job.id}`}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300",
              blurred && "pointer-events-none",
            )}
            tabIndex={blurred ? -1 : 0}
          >
            <Sparkles className="w-4 h-4" />
            Tailor Resume
          </Link>
          <button
            type="button"
            onClick={handleTrackApplication}
            disabled={trackLoading || blurred}
            data-testid={`track-application-${job.id}`}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm hover:border-slate-600 disabled:opacity-40"
          >
            {trackLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <ClipboardList className="w-4 h-4" />
            )}
            Track application
          </button>
          {job.apply_url && (
            <a
              href={job.apply_url}
              target="_blank"
              rel="noopener noreferrer"
              className={clsx(
                "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm hover:border-slate-600",
                blurred && "pointer-events-none opacity-40",
              )}
              tabIndex={blurred ? -1 : 0}
            >
              <ExternalLink className="w-4 h-4" />
              Apply
            </a>
          )}
          <button
            type="button"
            onClick={handleSave}
            disabled={saveLoading || blurred}
            aria-pressed={saved}
            className={clsx(
              "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-sm disabled:opacity-40",
              saved
                ? "border-amber-400/40 bg-amber-500/10 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300"
                : "border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 hover:border-slate-600",
            )}
          >
            {saveLoading ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : saved ? (
              <BookmarkCheck className="w-4 h-4" />
            ) : (
              <Bookmark className="w-4 h-4" />
            )}
            {saved ? "Bookmarked" : "Bookmark"}
          </button>
        </div>
      </div>

      {blurred && (
        <div className="absolute inset-0 flex items-center justify-center bg-slate-50/60 dark:bg-slate-950/60 backdrop-blur-[1px]">
          <Link
            href="/billing"
            className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300 shadow-lg"
          >
            Upgrade to view more jobs
          </Link>
        </div>
      )}
    </article>
  )
}
