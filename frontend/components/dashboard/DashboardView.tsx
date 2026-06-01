"use client"

import { useCallback, useEffect, useMemo, useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  Bell,
  Copy,
  Download,
  ExternalLink,
  FileText,
  Loader2,
  Plus,
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
} from "@/lib/dashboard"
import { listExports, type ExportListItem } from "@/lib/account"
import { isSubscriptionActive } from "@/lib/billing"

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
  draft: "bg-slate-700 text-slate-200",
  applied: "bg-blue-900/60 text-blue-200",
  interviewing: "bg-violet-900/60 text-violet-200",
  offer: "bg-emerald-900/60 text-emerald-200",
  rejected: "bg-red-900/60 text-red-200",
  withdrawn: "bg-slate-800 text-slate-400",
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  })
}

function AtsBadge({ score, delta }: { score: number; delta: number }) {
  const deltaLabel =
    delta === 0 ? null : delta > 0 ? `+${delta}` : String(delta)
  return (
    <span className="inline-flex items-center gap-1.5 text-xs font-semibold">
      <span className="bg-amber-400/15 text-amber-300 border border-amber-400/30 px-2 py-0.5 rounded-full tabular-nums">
        ATS {score}
      </span>
      {deltaLabel && (
        <span
          className={clsx(
            "tabular-nums",
            delta > 0 ? "text-emerald-400" : "text-red-400",
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
      <div className="flex justify-between text-xs text-slate-400 mb-1">
        <span>{label}</span>
        <span className="tabular-nums">
          {used}/{limit}
        </span>
      </div>
      <div className="h-2 bg-slate-800 rounded-full overflow-hidden">
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

  const loadSummary = useCallback(async () => {
    const data = await getDashboardSummary(token)
    setSummary(data)
    try {
      const history = await listExports(token)
      setExports(history)
    } catch {
      setExports([])
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
          setError(e instanceof Error ? e.message : "Failed to load dashboard")
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

  const handleBulkDelete = async () => {
    if (selected.size === 0) return
    await bulkResumeAction(token, { action: "delete", ids: [...selected] })
    setSelected(new Set())
    await loadResumes()
    await loadSummary()
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

  const handleDelete = async (id: string) => {
    await deleteResume(token, id)
    await loadResumes()
    await loadSummary()
  }

  if (loading) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  if (error) {
    return (
      <div className="max-w-6xl mx-auto px-4 py-12 text-center text-red-400">
        {error}
      </div>
    )
  }

  const sub = summary?.subscription
  const isSubscribed =
    !!sub && isSubscriptionActive(sub.status)
  const totalPages = Math.max(1, Math.ceil(total / 10))

  return (
    <main className="max-w-6xl mx-auto px-4 py-8 space-y-8">
      <header className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-white">
            Welcome back, {summary?.display_name ?? "there"}
          </h1>
          <div className="flex flex-wrap items-center gap-2 mt-2">
            <span className="text-xs font-semibold uppercase tracking-wide bg-amber-400/15 text-amber-300 border border-amber-400/30 px-2.5 py-1 rounded-full">
              {summary?.tier ?? "free"}
            </span>
            {isSubscribed && sub ? (
              <span className="text-sm text-slate-400">
                Next billing: {formatDate(sub.period_end)}
              </span>
            ) : (
              <span className="text-sm text-slate-400">
                {summary?.credit_balance ?? 0} credits remaining
              </span>
            )}
          </div>
        </div>
        <button
          type="button"
          className="relative p-2 rounded-lg border border-slate-700 text-slate-400 hover:text-slate-200"
          title="Notifications (coming soon)"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
        </button>
      </header>

      <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
        {[
          { href: "/session/new", label: "New tailored resume", icon: Plus },
          { href: "/profile", label: "Edit master resume", icon: FileText },
          { href: "/jobs", label: "Search jobs", icon: Search },
          { href: "/cover-letter/new", label: "Generate cover letter", icon: Sparkles },
        ].map(({ href, label, icon: Icon }) => (
          <Link
            key={href}
            href={href}
            className="flex items-center gap-2 bg-slate-900/80 border border-slate-800 rounded-xl px-4 py-3 text-sm text-slate-200 hover:border-amber-400/40 transition-colors"
          >
            <Icon className="w-4 h-4 text-amber-400 shrink-0" />
            {label}
          </Link>
        ))}
      </section>

      <div className="grid lg:grid-cols-3 gap-6">
        <section className="lg:col-span-1 bg-slate-900/80 border border-slate-800 rounded-xl p-5 space-y-4">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">
            Subscription
          </h2>
          {isSubscribed && sub ? (
            <>
              <p className="text-lg font-semibold text-white capitalize">
                {sub.plan} · {sub.billing_cycle}
              </p>
              {sub.trial_ends_at && (
                <p className="text-xs text-amber-300">
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
              <p className="text-slate-400 text-sm">
                Free tier — {summary?.credit_balance ?? 0} credits left.
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
          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="w-4 h-4 text-amber-400" />
              <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide">
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
                  <div className="mt-2 text-xs text-slate-400">
                    <span className="text-slate-300">
                      {formatDate(selectedTrendPoint.date)}:
                    </span>{" "}
                    ATS {selectedTrendPoint.score}
                    {selectedTrendPoint.jd_title && (
                      <>
                        {" "}for{" "}
                        <span className="text-slate-300">
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
              <p className="text-sm text-slate-500 py-8 text-center">
                Complete Phase 4 to see your ATS trend.
              </p>
            )}
          </div>

          <div className="bg-slate-900/80 border border-slate-800 rounded-xl p-5">
            <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wide mb-4">
              Recent activity
            </h2>
            <ul className="space-y-3">
              {(summary?.recent_activity ?? []).slice(0, 10).map((item, i) => (
                <li key={`${item.type}-${item.at}-${i}`} className="flex gap-3 text-sm">
                  <span className="text-slate-500 shrink-0 tabular-nums">{formatDate(item.at)}</span>
                  <div>
                    <p className="text-slate-200">{item.title}</p>
                    {item.subtitle && <p className="text-slate-500 text-xs">{item.subtitle}</p>}
                  </div>
                </li>
              ))}
              {!summary?.recent_activity?.length && (
                <li className="text-sm text-slate-500">No activity yet.</li>
              )}
            </ul>
          </div>
        </section>
      </div>

      {exports.length > 0 && (
        <section className="space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="text-lg font-semibold text-white">Data exports</h2>
            <Link href="/settings/danger" className="text-xs text-amber-400 hover:text-amber-300">
              Manage exports
            </Link>
          </div>
          <ul className="bg-slate-900/80 border border-slate-800 rounded-xl divide-y divide-slate-800">
            {exports.map((exp) => (
              <li key={exp.id} className="px-4 py-3 flex flex-wrap items-center justify-between gap-2 text-sm">
                <div>
                  <span className="text-slate-200 capitalize">{exp.status}</span>
                  <span className="text-slate-500 ml-2">{formatDate(exp.created_at)}</span>
                </div>
                {exp.status === "ready" && exp.presigned_url && (
                  <a
                    href={exp.presigned_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 text-amber-400 hover:text-amber-300"
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

      <section className="space-y-4">
        <h2 className="text-lg font-semibold text-white">
          Resume history
          <span className="text-slate-500 font-normal text-sm ml-2">
            ({summary?.counts.resumes ?? 0} total)
          </span>
        </h2>

        <div className="bg-slate-900/60 border border-slate-800 rounded-xl p-4 space-y-3">
          <div className="flex flex-wrap gap-3">
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-500" />
              <input
                type="search"
                placeholder="Search title, company, tags…"
                value={search}
                onChange={(e) => { setSearch(e.target.value); setPage(1) }}
                className="w-full pl-9 pr-3 py-2 bg-slate-950 border border-slate-700 rounded-lg text-sm text-slate-200"
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
              className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200 min-w-[180px] h-[84px]"
              aria-label="Status filters"
            >
              {STATUS_OPTIONS.filter((o) => o.value).map((o) => (
                <option key={o.value} value={o.value}>{o.label}</option>
              ))}
            </select>
            <input type="date" value={dateFrom} onChange={(e) => { setDateFrom(e.target.value); setPage(1) }} className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" aria-label="From date" />
            <input type="date" value={dateTo} onChange={(e) => { setDateTo(e.target.value); setPage(1) }} className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200" aria-label="To date" />
            <select value={sort} onChange={(e) => setSort(e.target.value as ResumeSort)} className="bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-200">
              <option value="date">Sort: Date</option>
              <option value="ats_score">Sort: ATS score</option>
              <option value="company">Sort: Company</option>
            </select>
          </div>
          <div className="flex flex-wrap items-center gap-4 text-sm text-slate-400">
            <label className="flex items-center gap-2">ATS min: {atsMin}
              <input type="range" min={0} max={100} value={atsMin} onChange={(e) => { setAtsMin(Number(e.target.value)); setPage(1) }} className="w-24" />
            </label>
            <label className="flex items-center gap-2">ATS max: {atsMax}
              <input type="range" min={0} max={100} value={atsMax} onChange={(e) => { setAtsMax(Number(e.target.value)); setPage(1) }} className="w-24" />
            </label>
            <button type="button" onClick={() => void loadResumes()} className="text-amber-400 hover:text-amber-300 text-xs font-medium">Apply filters</button>
          </div>
        </div>

        {selected.size > 0 && (
          <div className="flex items-center gap-3 bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-2 text-sm">
            <span className="text-slate-300">{selected.size} selected</span>
            <button type="button" onClick={() => void handleBulkTag()} className="text-amber-400 hover:text-amber-300 flex items-center gap-1">
              Tag
            </button>
            <button type="button" onClick={() => void handleBulkExport()} className="text-blue-400 hover:text-blue-300 flex items-center gap-1">
              Export
            </button>
            <button type="button" onClick={() => void handleBulkDelete()} className="text-red-400 hover:text-red-300 flex items-center gap-1">
              <Trash2 className="w-3.5 h-3.5" /> Delete
            </button>
          </div>
        )}

        {listLoading ? (
          <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-amber-400" /></div>
        ) : resumes.length === 0 ? (
          <div className="text-center py-12 text-slate-500 border border-dashed border-slate-800 rounded-xl">
            No resumes match your filters.{" "}
            <Link href="/session/new" className="text-amber-400 hover:underline">Build one</Link>
          </div>
        ) : (
          <div className="space-y-3">
            {resumes.map((r) => (
              <article key={r.id} className="bg-slate-900/80 border border-slate-800 rounded-xl p-4">
                <div className="flex flex-wrap items-start gap-3">
                  <input type="checkbox" checked={selected.has(r.id)} onChange={() => toggleSelect(r.id)} className="mt-1" aria-label={`Select ${r.jd_title}`} />
                  <div className="flex-1 min-w-0">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="font-semibold text-slate-100">{r.jd_title}</h3>
                      <span className="text-slate-500 text-sm">@ {r.jd_company}</span>
                      <span className={clsx("text-[10px] font-semibold uppercase px-2 py-0.5 rounded-full", STATUS_COLORS[r.status] ?? STATUS_COLORS.draft)}>{r.status}</span>
                    </div>
                    <div className="flex flex-wrap items-center gap-3 mt-2 text-xs text-slate-500">
                      <span>Built {formatDate(r.updated_at)}</span>
                      <AtsBadge score={r.current_ats_score} delta={r.ats_score_delta} />
                      {r.tags.map((t) => (<span key={t} className="bg-slate-800 text-slate-400 px-2 py-0.5 rounded">{t}</span>))}
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link href={`/session/${r.session_id}`} className="inline-flex items-center gap-1 text-xs font-medium text-slate-300 bg-slate-800 px-2.5 py-1.5 rounded-lg"><ExternalLink className="w-3.5 h-3.5" /> Open</Link>
                    <button type="button" onClick={() => void handleDuplicate(r.id)} className="inline-flex items-center gap-1 text-xs font-medium text-slate-300 bg-slate-800 px-2.5 py-1.5 rounded-lg"><Copy className="w-3.5 h-3.5" /> Duplicate</button>
                    <button type="button" onClick={() => void downloadResume(token, r.id, "pdf", `${r.jd_company}_resume.pdf`)} className="inline-flex items-center gap-1 text-xs font-medium text-slate-300 bg-slate-800 px-2.5 py-1.5 rounded-lg"><Download className="w-3.5 h-3.5" /> PDF</button>
                    <button type="button" onClick={() => void handleDelete(r.id)} className="inline-flex items-center gap-1 text-xs font-medium text-red-400 bg-slate-800 px-2.5 py-1.5 rounded-lg"><Trash2 className="w-3.5 h-3.5" /></button>
                  </div>
                </div>
                {expandedResumeId === r.id && summary && (
                  <div className="mt-4 h-24 border-t border-slate-800 pt-4">
                    <div className="overflow-x-auto">
                      <LineChart width={720} height={84} data={summary.ats_trend.filter((p) => p.resume_id === r.id)}>
                        <XAxis dataKey="date" tick={{ fontSize: 10, fill: "#64748b" }} />
                        <YAxis domain={[0, 100]} width={24} tick={{ fontSize: 10, fill: "#64748b" }} />
                        <Line type="monotone" dataKey="score" stroke="#fbbf24" dot />
                      </LineChart>
                    </div>
                  </div>
                )}
                <button type="button" onClick={() => setExpandedResumeId((id) => (id === r.id ? null : r.id))} className="mt-2 text-[10px] text-slate-500 hover:text-amber-400">
                  {expandedResumeId === r.id ? "Hide score trend" : "Show score trend"}
                </button>
              </article>
            ))}
          </div>
        )}

        {totalPages > 1 && (
          <div className="flex justify-center gap-2 pt-2">
            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="px-3 py-1.5 text-sm rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40">Previous</button>
            <span className="text-sm text-slate-500 self-center">Page {page} of {totalPages}</span>
            <button type="button" disabled={page >= totalPages} onClick={() => setPage((p) => p + 1)} className="px-3 py-1.5 text-sm rounded-lg bg-slate-800 text-slate-300 disabled:opacity-40">Next</button>
          </div>
        )}
      </section>
    </main>
  )
}
