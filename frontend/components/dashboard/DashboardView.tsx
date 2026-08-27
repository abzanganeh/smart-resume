"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Bell,
  Copy,
  Download,
  ExternalLink,
  Loader2,
  Pencil,
  Search,
  Sparkles,
  Trash2,
  TrendingUp,
} from "lucide-react"
import {
  Line,
  LineChart,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts"
import { clsx } from "clsx"
import { signOut } from "next-auth/react"
import type {
  DashboardSummaryResponse,
  ResumeListItem,
  ResumeRecordStatus,
  ResumeSort,
} from "@/lib/api"
import {
  bulkResumeAction,
  deleteResume,
  downloadResume,
  duplicateResume,
  getDashboardSummary,
  listResumes,
  patchResume,
} from "@/lib/dashboard"
import { listExports, type ExportListItem } from "@/lib/account"
import { isSubscriptionActive } from "@/lib/billing"
import { isStaleAuthError } from "@/lib/auth/staleSession"
import { getProfileResume, type ProfileResume } from "@/lib/profile"
import { getJobPreferences } from "@/lib/jobs"
import { getApplicationFunnel } from "@/lib/tracker"
import { DashboardStepStack } from "@/components/dashboard/DashboardStepStack"

const STATUS_OPTIONS: { value: ResumeRecordStatus | ""; label: string }[] = [
  { value: "", label: "All statuses" },
  { value: "draft", label: "Draft" },
  { value: "applied", label: "Applied" },
  { value: "interviewing", label: "Interviewing" },
  { value: "offer", label: "Offer" },
  { value: "rejected", label: "Rejected" },
  { value: "withdrawn", label: "Withdrawn" },
]

const STATUS_COLORS: Record<string, string> = {
  draft: "bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-200",
  applied: "bg-blue-50 dark:bg-blue-900/60 text-blue-800 dark:text-blue-200",
  interviewing: "bg-violet-50 dark:bg-violet-900/60 text-violet-800 dark:text-violet-200",
  offer: "bg-emerald-50 dark:bg-emerald-900/60 text-emerald-800 dark:text-emerald-200",
  rejected: "bg-red-50 dark:bg-red-900/60 text-red-800 dark:text-red-200",
  withdrawn: "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400",
}

const TAILORING_COLORS: Record<string, string> = {
  in_progress: "bg-amber-50 dark:bg-amber-900/50 text-amber-800 dark:text-amber-200 border border-amber-200 dark:border-amber-700/40",
  polished: "bg-emerald-50 dark:bg-emerald-900/50 text-emerald-800 dark:text-emerald-200 border border-emerald-200 dark:border-emerald-700/40",
}

function resumeTitle(r: ResumeListItem): string {
  return r.display_name?.trim() || r.jd_title
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function isResumeNotFoundError(err: unknown): boolean {
  if (!(err instanceof Error)) return false
  const msg = err.message.toLowerCase()
  return msg.includes("not found") || msg.includes("http 404")
}

function AtsBadge({
  score,
  delta,
  tailoringStage,
}: {
  score: number
  delta: number
  tailoringStage: ResumeListItem["tailoring_stage"]
}) {
  if (tailoringStage === "in_progress" && score === 0) {
    return (
      <span className="text-xs text-slate-600 dark:text-slate-400 italic">Not scored yet</span>
    )
  }
  const deltaLabel =
    delta === 0 ? null : delta > 0 ? `+${delta}` : String(delta)
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
      <span className="bg-amber-500/15 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 border border-amber-400/30 px-2 py-0.5 rounded-full tabular-nums">
        ATS {score}
      </span>
      {deltaLabel && (
        <span
          className={clsx(
            "tabular-nums",
            delta > 0 ? "text-emerald-700 dark:text-emerald-400" : "text-red-700 dark:text-red-400",
          )}
        >
          {deltaLabel}
        </span>
      )}
    </span>
  )
}

function UsageBar({
  label,
  used,
  limit,
}: {
  label: string
  used: number
  limit: number
}) {
  const pct = limit > 0 ? Math.min(100, (used / limit) * 100) : 0
  return (
    <div>
      <div className="flex justify-between text-xs text-slate-600 dark:text-slate-400 mb-1">
        <span>{label}</span>
        <span className="tabular-nums">
          {used}/{limit}
        </span>
      </div>
      <div className="h-2 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-amber-400 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  )
}

export function DashboardView({ token }: { token: string }) {
  const router = useRouter()

  const [summary, setSummary] = useState<DashboardSummaryResponse | null>(null)
  const [resumes, setResumes] = useState<ResumeListItem[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [listLoading, setListLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [search, setSearch] = useState("")
  const [statusFilters, setStatusFilters] = useState<ResumeRecordStatus[]>([])
  const [dateFrom, setDateFrom] = useState("")
  const [dateTo, setDateTo] = useState("")
  const [atsMin, setAtsMin] = useState(0)
  const [atsMax, setAtsMax] = useState(100)
  const [sort, setSort] = useState<ResumeSort>("date")
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [expandedResumeId, setExpandedResumeId] = useState<string | null>(null)
  const [selectedTrendPoint, setSelectedTrendPoint] = useState<{
    date: string
    score: number
    jd_title?: string
    jd_company?: string
  } | null>(null)
  const [exports, setExports] = useState<ExportListItem[]>([])
  const [masterProfile, setMasterProfile] = useState<ProfileResume | null>(null)
  const [preferredTitles, setPreferredTitles] = useState<string[]>([])
  const [jobRolesReady, setJobRolesReady] = useState(false)
  const [jobRolesStale, setJobRolesStale] = useState(false)
  const [applicationCounts, setApplicationCounts] = useState<{
    active: number
    interviewing: number
    offer: number
    total: number
  } | null>(null)
  const [deletingIds, setDeletingIds] = useState<Set<string>>(new Set())

  const masterChunkCount =
    masterProfile?.chunk_count ?? summary?.counts.master_chunks ?? 0
  const hasMasterResume = masterChunkCount > 0

  const loadSummary = useCallback(async () => {
    const data = await getDashboardSummary(token)
    setSummary(data)
    try {
      const history = await listExports(token)
      setExports(history)
    } catch {
      setExports([])
    }
    try {
      const profile = await getProfileResume(token)
      setMasterProfile(profile)
    } catch {
      setMasterProfile(null)
    }
    try {
      const prefs = await getJobPreferences(token)
      setPreferredTitles(prefs.preferred_titles ?? [])
      setJobRolesReady(Boolean(prefs.preferred_titles_confirmed))
      setJobRolesStale(Boolean(prefs.preferred_titles_stale))
    } catch {
      setPreferredTitles([])
      setJobRolesReady(false)
      setJobRolesStale(false)
    }
    try {
      // /api/applications/funnel returns aggregate per-status counts plus
      // ``total`` in one round-trip so we don't over-fetch full row payloads
      // just to compute a handful of scalars.
      const funnel = await getApplicationFunnel(token)
      const counts = funnel.status_counts
      setApplicationCounts({
        active: (counts.draft ?? 0) + (counts.applied ?? 0),
        interviewing: counts.interviewing ?? 0,
        offer: (counts.offer ?? 0) + (counts.accepted ?? 0),
        total: funnel.total,
      })
    } catch {
      setApplicationCounts(null)
    }
  }, [token])

  const loadResumes = useCallback(async () => {
    setListLoading(true)
    try {
      const data = await listResumes(token, {
        q: search || undefined,
        statuses: statusFilters.length ? statusFilters : undefined,
        date_from: dateFrom ? `${dateFrom}T00:00:00Z` : undefined,
        date_to: dateTo ? `${dateTo}T23:59:59Z` : undefined,
        ats_min: atsMin > 0 ? atsMin : undefined,
        ats_max: atsMax < 100 ? atsMax : undefined,
        sort,
        page,
        page_size: 10,
      })
      setResumes(data.items)
      setTotal(data.total)
    } finally {
      setListLoading(false)
    }
  }, [token, search, statusFilters, dateFrom, dateTo, atsMin, atsMax, sort, page])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      setLoading(true)
      setError(null)
      try {
        await loadSummary()
        await loadResumes()
      } catch (e) {
        if (!cancelled) {
          const raw = e instanceof Error ? e.message : "Failed to load dashboard"
          if (isStaleAuthError(raw)) {
            void signOut({ callbackUrl: "/auth?callbackUrl=%2Fdashboard" })
            return
          }
          const friendly =
            raw.includes("sqlalchemy") || raw.startsWith("Server error:")
              ? "We couldn't load your dashboard. Please refresh the page."
              : raw
          setError(friendly)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [loadSummary, loadResumes])

  const sparklineData = useMemo(() => {
    if (!summary?.ats_trend.length) return []
    const byDate = new Map<string, number>()
    for (const point of summary.ats_trend) {
      byDate.set(point.date, point.score)
    }
    return [...byDate.entries()].map(([date, score]) => ({ date, score }))
  }, [summary])

  const toggleSelect = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const removeResumesFromList = (ids: Iterable<string>) => {
    const idSet = new Set(ids)
    setResumes((prev) => prev.filter((item) => !idSet.has(item.id)))
    setSelected((prev) => {
      const next = new Set(prev)
      for (const id of idSet) next.delete(id)
      return next
    })
    if (expandedResumeId && idSet.has(expandedResumeId)) {
      setExpandedResumeId(null)
    }
  }

  const refreshAfterDelete = async () => {
    try {
      await loadResumes()
      await loadSummary()
    } catch (e) {
      const raw = e instanceof Error ? e.message : "Failed to refresh dashboard"
      if (isStaleAuthError(raw)) {
        void signOut({ callbackUrl: "/auth?callbackUrl=%2Fdashboard" })
        return
      }
      setError(
        raw.includes("sqlalchemy") || raw.startsWith("Server error:")
          ? "We couldn't refresh your dashboard. Please reload the page."
          : raw,
      )
    }
  }

  const handleBulkDelete = async () => {
    if (selected.size === 0) return
    const ids = [...selected]
    try {
      await bulkResumeAction(token, { action: "delete", ids })
    } catch (e) {
      if (!isResumeNotFoundError(e)) {
        setError(e instanceof Error ? e.message : "Bulk delete failed")
        return
      }
    }
    removeResumesFromList(ids)
    await refreshAfterDelete()
  }

  const handleBulkTag = async () => {
    if (selected.size === 0) return
    const raw = window.prompt("Enter tags (comma separated)")
    if (!raw) return
    const tags = raw
      .split(",")
      .map((t) => t.trim())
      .filter(Boolean)
    if (!tags.length) return
    await bulkResumeAction(token, { action: "tag", ids: [...selected], tags })
    await loadResumes()
  }

  const handleRename = async (r: ResumeListItem) => {
    const suggested = r.display_name?.trim() || r.jd_title
    const raw = window.prompt("Name this resume", suggested)
    if (raw === null) return
    const updated = await patchResume(token, r.id, {
      display_name: raw.trim() || null,
    })
    setResumes((prev) =>
      prev.map((item) => (item.id === r.id ? { ...item, ...updated } : item)),
    )
  }

  const handleBulkExport = async () => {
    if (selected.size === 0) return
    const result = await bulkResumeAction(token, {
      action: "export",
      ids: [...selected],
    })
    for (const entry of result.exports ?? []) {
      await downloadResume(
        token,
        entry.id,
        "zip",
        `${entry.company.replace(/\s+/g, "_")}_resume.zip`,
      )
    }
  }

  const handleDuplicate = async (id: string) => {
    const { session_id } = await duplicateResume(token, id)
    router.push(`/session/${session_id}`)
  }

  const handleDelete = async (id: string, title: string) => {
    if (deletingIds.has(id)) return

    const confirmed = window.confirm(
      `Delete "${title}"?\n\nThis is permanent. Credits already spent on generation are not refunded.`,
    )
    if (!confirmed) return

    setDeletingIds((prev) => new Set(prev).add(id))
    try {
      await deleteResume(token, id)
    } catch (e) {
      if (!isResumeNotFoundError(e)) {
        setError(e instanceof Error ? e.message : "Delete failed")
        return
      }
      // Already deleted server-side — drop the stale row and resync.
    } finally {
      setDeletingIds((prev) => {
        const next = new Set(prev)
        next.delete(id)
        return next
      })
    }

    removeResumesFromList([id])
    await refreshAfterDelete()
  }

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12 text-center text-red-700 dark:text-red-400">
        {error}
      </div>
    )
  }

  const sub = summary?.subscription
  const isSubscribed =
    !!sub && isSubscriptionActive(sub.status)
  const totalPages = Math.max(1, Math.ceil(total / 10))

  return (
    <main className="min-h-[60vh] bg-sr-bg max-w-6xl mx-auto px-4 py-8 space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-900 dark:text-white">
            Welcome back, {summary?.display_name ?? "there"}
          </h1>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="text-xs font-semibold uppercase tracking-wide bg-amber-500/15 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 border border-amber-400/30 px-2.5 py-1 rounded-full">
              {summary?.tier ?? "free"}
            </span>
            {isSubscribed && sub ? (
              <span className="text-sm text-slate-600 dark:text-slate-400">
                Next billing: {formatDate(sub.period_end)}
              </span>
            ) : summary?.credits_locked_until_verification ? (
              <span className="text-sm text-amber-700 dark:text-amber-300">
                {summary?.credit_balance ?? 0} credits — verify email to use
              </span>
            ) : (
              <span className="text-sm text-slate-600 dark:text-slate-400">
                {summary?.credit_balance ?? 0} credits remaining
              </span>
            )}
          </div>
        </div>
      </header>

      <DashboardStepStack
        hasMasterResume={hasMasterResume}
        masterChunkCount={masterChunkCount}
        masterUpdatedAt={masterProfile?.last_embedded_at ?? null}
        jobRolesReady={jobRolesReady}
        jobRolesStale={jobRolesStale}
        hasJd={
          (summary?.counts.job_descriptions ?? 0) > 0 ||
          (summary?.counts.saved_jobs ?? 0) > 0 ||
          (summary?.counts.resumes ?? 0) > 0
        }
        preferredTitles={preferredTitles}
        tailoredResumeCount={summary?.counts.resumes ?? 0}
        applicationCounts={applicationCounts}
        formatDate={formatDate}
      />

      <div className="pt-4 border-t border-slate-200 dark:border-slate-800">
        <h2 className="text-xs font-semibold uppercase tracking-widest text-slate-500 dark:text-slate-400 mb-3">
          Your workspace
        </h2>
        <section className="grid grid-cols-2 md:grid-cols-3 gap-3">
          {[
            { href: "/fit", label: "Job fit analysis", icon: TrendingUp },
            { href: "/cover-letter/new", label: "Cover letter", icon: Sparkles },
            { href: "/career-watch", label: "Career Watch", icon: Bell },
          ].map(({ href, label, icon: Icon }) => (
            <Link
              key={href}
              href={href}
              className="flex items-center gap-2 bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-700 dark:text-slate-200 hover:border-amber-400/40 transition-colors"
            >
              <Icon className="w-4 h-4 text-amber-700 dark:text-amber-400 shrink-0" />
              {label}
            </Link>
          ))}
        </section>
      </div>

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-1 bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
            Subscription
          </h2>
          {isSubscribed && sub ? (
            <>
              <p className="text-lg font-semibold text-slate-900 dark:text-white capitalize">
                {sub.plan} · {sub.billing_cycle}
              </p>
              {sub.trial_ends_at && (
                <p className="text-xs text-amber-700 dark:text-amber-300">
                  Trial ends {formatDate(sub.trial_ends_at)}
                </p>
              )}
              <UsageBar label="Resumes this period" used={sub.resumes_used} limit={sub.resumes_limit} />
              <UsageBar label="Searches this period" used={sub.searches_used} limit={sub.searches_limit} />
              <Link
                href="/billing"
                className="block text-center text-xs font-semibold bg-amber-400 text-slate-900 py-2 rounded-lg hover:bg-amber-300"
              >
                Manage plan
              </Link>
            </>
          ) : (
            <>
              <p className="text-slate-600 dark:text-slate-400 text-sm">
                {summary?.credits_locked_until_verification
                  ? `Free tier — ${summary?.credit_balance ?? 0} credits waiting. Verify your email in Settings to use them.`
                  : `Free tier — ${summary?.credit_balance ?? 0} credits left.`}
              </p>
              <Link
                href="/billing"
                className="block text-center text-xs font-semibold bg-amber-400 text-slate-900 py-2 rounded-lg hover:bg-amber-300"
              >
                Upgrade
              </Link>
            </>
          )}
        </section>

        <section className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
                ATS score trend (30 days)
              </h2>
            </div>
            {sparklineData.length > 0 ? (
              <div className="h-36 overflow-x-auto">
                <LineChart
                  width={760}
                  height={144}
                  data={sparklineData}
                  onClick={(state: unknown) => {
                    const payload = (state as { activePayload?: Array<{ payload?: unknown }> } | null)?.activePayload?.[0]?.payload as
                      | { date: string; score: number }
                      | undefined
                    if (!payload) return
                    const source = summary?.ats_trend.find(
                      (p) =>
                        p.date === payload.date &&
                        p.score === payload.score,
                    )
                    setSelectedTrendPoint({
                      date: payload.date,
                      score: payload.score,
                      jd_title: source?.jd_title,
                      jd_company: source?.jd_company,
                    })
                  }}
                >
                  <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 10 }} />
                  <YAxis domain={[0, 100]} tick={{ fill: "#64748b", fontSize: 10 }} width={28} />
                  <Tooltip
                    contentStyle={{
                      background: "#0f172a",
                      border: "1px solid #334155",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Line type="monotone" dataKey="score" stroke="#fbbf24" strokeWidth={2} dot={{ r: 3, fill: "#fbbf24" }} />
                </LineChart>
                {selectedTrendPoint && (
                  <div className="mt-2 text-xs text-slate-600 dark:text-slate-400">
                    <span className="text-slate-700 dark:text-slate-300">
                      {formatDate(selectedTrendPoint.date)}:
                    </span>{" "}
                    ATS {selectedTrendPoint.score}
                    {selectedTrendPoint.jd_title && (
                      <>
                        {" "}for{" "}
                        <span className="text-slate-700 dark:text-slate-300">
                          {selectedTrendPoint.jd_title}
                        </span>
                        {selectedTrendPoint.jd_company
                          ? ` @ ${selectedTrendPoint.jd_company}`
                          : ""}
                      </>
                    )}
                  </div>
                )}
              </div>
            ) : (
              <p className="text-sm text-slate-600 dark:text-slate-400 py-8 text-center">
                Complete Phase 4 to see your ATS trend.
              </p>
            )}
          </div>

          <div className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide mb-4">
              Recent activity
            </h2>
            <ul className="space-y-3">
              {(summary?.recent_activity ?? []).slice(0, 10).map((item, i) => (
                <li key={`${item.type}-${item.at}-${i}`} className="flex gap-3 text-sm">
                  <span className="text-slate-600 dark:text-slate-400 shrink-0 tabular-nums">{formatDate(item.at)}</span>
                  <div>
                    <p className="text-slate-700 dark:text-slate-200">{item.title}</p>
                    {item.subtitle && <p className="text-slate-600 dark:text-slate-400 text-xs">{item.subtitle}</p>}
                  </div>
                </li>
              ))}
              {!summary?.recent_activity?.length && (
                <li className="text-sm text-slate-600 dark:text-slate-400">No activity yet.</li>
              )}
            </ul>
          </div>
        </section>
      </div>

      {exports.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">Data exports</h2>
            <Link href="/settings/danger" className="text-xs text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300">
              Manage exports
            </Link>
          </div>
          <ul className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl divide-y divide-slate-200 dark:divide-slate-800">
            {exports.map((exp) => (
              <li key={exp.id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                <div>
                  <span className="text-slate-700 dark:text-slate-200 capitalize">{exp.status}</span>
                  <span className="text-slate-600 dark:text-slate-400 ml-2">{formatDate(exp.created_at)}</span>
                </div>
                {exp.status === "ready" && exp.presigned_url && (
                  <a
                    href={exp.presigned_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300"
                  >
                    <Download className="w-3.5 h-3.5" />
                    Download
                  </a>
                )}
              </li>
            ))}
          </ul>
        </section>
      )}

      <section className="space-y-4" id="tailored-resumes">
        <div>
          <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
            Tailored resumes
            <span className="text-slate-600 dark:text-slate-400 font-normal text-sm ml-2">
              ({summary?.counts.resumes ?? 0} total)
            </span>
          </h2>
          <p className="text-sm text-slate-600 dark:text-slate-400 mt-1">
            Job-specific versions built from your master resume — each gets its own ATS score and history.
          </p>
        </div>

        <div className="bg-slate-50 dark:bg-slate-900/60 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-600 dark:text-slate-400" />
              <input
                type="search"
                placeholder="Search title, company, tags…"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                className="w-full pl-9 pr-3 py-2 bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg text-sm text-slate-700 dark:text-slate-200"
              />
            </div>
            <select
              multiple
              value={statusFilters}
              onChange={(e) => {
                const values = Array.from(e.target.selectedOptions).map(
                  (opt) => opt.value as ResumeRecordStatus,
                )
                setStatusFilters(values.filter(Boolean))
                setPage(1)
              }}
              className="bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200 min-w-[180px] h-[84px]"
              aria-label="Status filters"
            >
              {STATUS_OPTIONS.filter((o) => o.value).map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200" aria-label="From date" />
            <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200" aria-label="To date" />
            <select value={sort} onChange={(e) => setSort(e.target.value as ResumeSort)} className="bg-white dark:bg-slate-950 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-700 dark:text-slate-200">
              <option value="date">Sort: Date</option>
              <option value="ats_score">Sort: ATS score</option>
              <option value="company">Sort: Company</option>
            </select>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600 dark:text-slate-400">
            <label className="flex items-center gap-2">ATS min: {atsMin}
              <input type="range" min={0} max={100} value={atsMin} onChange={(e) => { setAtsMin(Number(e.target.value)); setPage(1) }} className="w-24" />
            </label>
            <label className="flex items-center gap-2">ATS max: {atsMax}
              <input type="range" min={0} max={100} value={atsMax} onChange={(e) => { setAtsMax(Number(e.target.value)); setPage(1) }} className="w-24" />
            </label>
            <button type="button" onClick={() => void loadResumes()} className="text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 text-xs font-medium">Apply filters</button>
          </div>
        </div>

        {selected.size > 0 && (
          <div className="flex items-center gap-3 bg-slate-100 dark:bg-slate-800/80 border border-slate-300 dark:border-slate-700 rounded-lg px-4 py-2 text-sm">
            <span className="text-slate-700 dark:text-slate-300">{selected.size} selected</span>
            <button type="button" onClick={() => void handleBulkTag()} className="text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 flex items-center gap-1">
              Tag
            </button>
            <button type="button" onClick={() => void handleBulkExport()} className="text-blue-700 dark:text-blue-400 hover:text-blue-300 flex items-center gap-1">
              Export
            </button>
            <button type="button" onClick={() => void handleBulkDelete()} className="text-red-700 dark:text-red-400 hover:text-red-300 flex items-center gap-1">
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
          </div>
        )}

        {listLoading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-amber-700 dark:text-amber-400" /></div>
        ) : resumes.length === 0 ? (
          <div className="text-center py-12 text-slate-600 dark:text-slate-400 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl space-y-3 px-4">
            {hasMasterResume ? (
              <>
                <p>No tailored resumes yet.</p>
                <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto">
                  Your master resume is indexed and ready. Create a tailored version by
                  pasting a job description — it will appear here with ATS scores and export links.
                </p>
              </>
            ) : (
              <>
                <p>No tailored resumes yet.</p>
                <p className="text-sm text-slate-600 dark:text-slate-400 max-w-md mx-auto">
                  Upload or build your master resume first, then tailor it to each job you apply for.
                </p>
              </>
            )}
            <Link
              href="/session/new"
              className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400 hover:underline font-medium"
            >
              New tailored resume
            </Link>
          </div>
        ) : (
          <div className="space-y-3">
            {resumes.map((r) => (
              <article key={r.id} className="bg-white dark:bg-slate-900/80 border border-slate-200 dark:border-slate-800 rounded-xl p-4">
                <div className="flex flex-wrap items-start gap-3">
                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} className="mt-1" aria-label={`Select ${resumeTitle(r)}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-900 dark:text-slate-100">{resumeTitle(r)}</h3>
                      {r.display_name && (
                        <span className="text-slate-600 dark:text-slate-400 text-sm truncate">{r.jd_title}</span>
                      )}
                      <span className="text-slate-600 dark:text-slate-400 text-sm">@ {r.jd_company}</span>
                      <span className={clsx("text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full", TAILORING_COLORS[r.tailoring_stage] ?? TAILORING_COLORS.in_progress)}>
                        {r.tailoring_stage === "in_progress" ? "Draft" : "Polished"}
                      </span>
                      {r.tailoring_stage === "polished" && (
                        <span className={clsx("text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full", STATUS_COLORS[r.status] ?? STATUS_COLORS.draft)}>{r.status}</span>
                      )}
                    </div>
                    <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-slate-600 dark:text-slate-400">
                      <span>Built {formatDate(r.updated_at)}</span>
                      <AtsBadge score={r.current_ats_score} delta={r.ats_score_delta} tailoringStage={r.tailoring_stage} />
                      {r.tags.map((t) => (<span key={t} className="bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 px-2 py-0.5 rounded">{t}</span>))}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/session/${r.session_id}`} className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg"><ExternalLink className="w-3.5 h-3.5" /> Open</Link>
                    <button type="button" onClick={() => void handleRename(r)} className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg" title="Rename"><Pencil className="w-3.5 h-3.5" /> Name</button>
                    <button type="button" onClick={() => void handleDuplicate(r.id)} className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg"><Copy className="w-3.5 h-3.5" /> Duplicate</button>
                    <button type="button" onClick={() => void downloadResume(token, r.id, "pdf", `${r.jd_company}_resume.pdf`)} className="inline-flex items-center gap-1 text-xs font-medium text-slate-700 dark:text-slate-300 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg"><Download className="w-3.5 h-3.5" /> PDF</button>
                    <button
                      type="button"
                      disabled={deletingIds.has(r.id)}
                      onClick={() => void handleDelete(r.id, resumeTitle(r))}
                      className="inline-flex items-center gap-1 text-xs font-medium text-red-700 dark:text-red-400 bg-slate-100 dark:bg-slate-800 px-2.5 py-1.5 rounded-lg disabled:opacity-40"
                      aria-label={`Delete ${resumeTitle(r)}`}
                    >
                      {deletingIds.has(r.id) ? (
                        <Loader2 className="w-3.5 h-3.5 animate-spin" />
                      ) : (
                        <Trash2 className="w-3.5 h-3.5" />
                      )}
                    </button>
                  </div>
                </div>
                {expandedResumeId === r.id && summary && (
                  <div className="mt-4 h-24 border-t border-slate-200 dark:border-slate-800 pt-4">
                    <div className="overflow-x-auto">
                      <LineChart width={720} height={84} data={summary.ats_trend.filter((p) => p.resume_id === r.id)}>
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} />
                        <YAxis domain={[0, 100]} width={24} tick={{ fontSize: 10, fill: "#64748b" }} />
                        <Line type="monotone" dataKey="score" stroke="#fbbf24" dot />
                      </LineChart>
                    </div>
                  </div>
                )}
                <button type="button" onClick={() => setExpandedResumeId((id) => (id === r.id ? null : r.id))} className="mt-2 text-[10px] text-slate-600 dark:text-slate-400 hover:text-amber-800 dark:hover:text-amber-400">
                  {expandedResumeId === r.id ? "Hide score trend" : "Show score trend"}
                </button>
              </article>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex justify-center gap-2 pt-2">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1.5 text-sm rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 disabled:opacity-40">Previous</button>
            <span className="text-sm text-slate-600 dark:text-slate-400 self-center">Page {page} of {totalPages}</span>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="px-3 py-1.5 text-sm rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 disabled:opacity-40">Next</button>
          </div>
        )}
      </section>
    </main>
  )
}
