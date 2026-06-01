"use client"

import { useEffect, useState } from "react"
import { ChevronLeft, ChevronRight, Loader2, Search } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession } from "@/app/admin/layout"
import { getAuditLog } from "@/lib/admin/api"
import type { AuditLogEntry } from "@/lib/admin/types"

const PER_PAGE = 50

// ── Audit Log Page ────────────────────────────────────────────────────────────

export default function AdminAuditPage() {
  const { token } = useAdminSession()

  const [entries, setEntries] = useState<AuditLogEntry[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  // Filters
  const [actor, setActor] = useState("")
  const [action, setAction] = useState("")
  const [targetType, setTargetType] = useState("")
  const today = new Date().toISOString().slice(0, 10)
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
  const [from, setFrom] = useState(thirtyDaysAgo)
  const [to, setTo] = useState(today)

  // Apply button to avoid re-fetching on every keystroke
  const [appliedFilters, setAppliedFilters] = useState({
    actor: "",
    action: "",
    targetType: "",
    from: thirtyDaysAgo,
    to: today,
  })

  useEffect(() => {
    if (!token) return
    loadLog()
  }, [token, page, appliedFilters]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadLog() {
    setLoading(true)
    setError(null)
    try {
      const res = await getAuditLog(token!, {
        actor: appliedFilters.actor || undefined,
        action: appliedFilters.action || undefined,
        target_type: appliedFilters.targetType || undefined,
        from: appliedFilters.from,
        to: appliedFilters.to,
        page,
        per_page: PER_PAGE,
      })
      setEntries(res.entries)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load audit log")
    } finally {
      setLoading(false)
    }
  }

  function applyFilters() {
    setPage(1)
    setAppliedFilters({ actor, action, targetType, from, to })
  }

  const totalPages = Math.ceil(total / PER_PAGE)

  if (!token) return <NotAuthed />

  return (
    <div className="space-y-5 max-w-6xl">
      <h1 className="text-xl font-semibold text-white">Audit Log</h1>

      {/* Filters */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-4 space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
          <FilterInput
            placeholder="Actor email"
            value={actor}
            onChange={setActor}
            icon={Search}
          />
          <FilterInput
            placeholder="Action (e.g. price_change)"
            value={action}
            onChange={setAction}
          />
          <FilterInput
            placeholder="Target type (e.g. user)"
            value={targetType}
            onChange={setTargetType}
          />
          <div className="flex gap-2">
            <input
              type="date"
              value={from}
              max={to}
              onChange={(e) => setFrom(e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
            <input
              type="date"
              value={to}
              min={from}
              max={today}
              onChange={(e) => setTo(e.target.value)}
              className="flex-1 bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-amber-500/50"
            />
          </div>
        </div>
        <button
          onClick={applyFilters}
          className="bg-amber-600 hover:bg-amber-500 text-white text-sm px-4 py-1.5 rounded-lg transition-colors"
        >
          Apply filters
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800">
          <span className="text-xs text-slate-400">{total} entries</span>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <Th>Time</Th>
                <Th>Actor</Th>
                <Th>Action</Th>
                <Th>Target</Th>
                <Th>IP</Th>
                <Th>ID</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {loading && (
                <tr>
                  <td colSpan={6} className="py-10 text-center">
                    <Loader2 className="w-6 h-6 animate-spin text-amber-400 mx-auto" />
                  </td>
                </tr>
              )}
              {!loading && entries.length === 0 && (
                <tr>
                  <td colSpan={6} className="py-10 text-center text-slate-500 text-sm">
                    No audit entries in range.
                  </td>
                </tr>
              )}
              {!loading &&
                entries.map((e) => (
                  <AuditRow key={e.id} entry={e} />
                ))}
            </tbody>
          </table>
        </div>

        {totalPages > 1 && (
          <div className="flex items-center justify-between px-5 py-3 border-t border-slate-800">
            <span className="text-xs text-slate-500">
              {(page - 1) * PER_PAGE + 1}–{Math.min(page * PER_PAGE, total)} of {total}
            </span>
            <div className="flex items-center gap-2">
              <button
                disabled={page <= 1}
                onClick={() => setPage((p) => p - 1)}
                className="p-1.5 rounded text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronLeft className="w-4 h-4" />
              </button>
              <span className="text-sm text-slate-400">
                {page} / {totalPages}
              </span>
              <button
                disabled={page >= totalPages}
                onClick={() => setPage((p) => p + 1)}
                className="p-1.5 rounded text-slate-400 hover:text-white disabled:opacity-30 transition-colors"
              >
                <ChevronRight className="w-4 h-4" />
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}

// ── Audit Row ─────────────────────────────────────────────────────────────────

function AuditRow({ entry }: { entry: AuditLogEntry }) {
  const [expanded, setExpanded] = useState(false)

  return (
    <>
      <tr
        className="hover:bg-slate-800/30 cursor-pointer transition-colors"
        onClick={() => setExpanded((v) => !v)}
      >
        <Td className="text-xs text-slate-500 whitespace-nowrap">
          {new Date(entry.created_at).toLocaleString()}
        </Td>
        <Td>
          <span className="text-xs text-slate-300 truncate max-w-[120px] block">
            {entry.admin_email}
          </span>
        </Td>
        <Td>
          <ActionBadge action={entry.action} />
        </Td>
        <Td className="text-xs text-slate-400">
          <span className="capitalize">{entry.target_type}</span>
          {entry.target_id && (
            <span className="font-mono text-slate-600 ml-1">
              {entry.target_id.slice(0, 8)}…
            </span>
          )}
        </Td>
        <Td className="font-mono text-xs text-slate-500">{entry.request_ip}</Td>
        <Td className="font-mono text-xs text-slate-600">{entry.id.slice(0, 8)}…</Td>
      </tr>
      {expanded && (entry.old_value || entry.new_value) && (
        <tr>
          <td colSpan={6} className="bg-slate-800/40 px-5 py-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs font-mono">
              {entry.old_value !== null && (
                <div>
                  <p className="text-slate-500 mb-1">Before</p>
                  <pre className="text-red-300/80 bg-red-900/20 rounded p-2 overflow-auto max-h-40">
                    {JSON.stringify(entry.old_value, null, 2)}
                  </pre>
                </div>
              )}
              {entry.new_value !== null && (
                <div>
                  <p className="text-slate-500 mb-1">After</p>
                  <pre className="text-emerald-300/80 bg-emerald-900/20 rounded p-2 overflow-auto max-h-40">
                    {JSON.stringify(entry.new_value, null, 2)}
                  </pre>
                </div>
              )}
            </div>
          </td>
        </tr>
      )}
    </>
  )
}

// ── Action badge ──────────────────────────────────────────────────────────────

const ACTION_COLORS: Record<string, string> = {
  price_change: "bg-amber-900/40 text-amber-300",
  credit_edit: "bg-blue-900/40 text-blue-300",
  user_suspend: "bg-red-900/40 text-red-300",
  user_unsuspend: "bg-emerald-900/40 text-emerald-300",
  model_change: "bg-violet-900/40 text-violet-300",
  flag_toggle: "bg-cyan-900/40 text-cyan-300",
  refund_approve: "bg-emerald-900/40 text-emerald-300",
  refund_deny: "bg-red-900/40 text-red-300",
  announcement_create: "bg-slate-700 text-slate-300",
  announcement_delete: "bg-red-900/30 text-red-400",
  user_delete: "bg-red-900/60 text-red-200",
}

function ActionBadge({ action }: { action: string }) {
  const cls = ACTION_COLORS[action] ?? "bg-slate-700 text-slate-300"
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded", cls)}>
      {action}
    </span>
  )
}

// ── Shared atoms ──────────────────────────────────────────────────────────────

function FilterInput({
  placeholder,
  value,
  onChange,
  icon: Icon,
}: {
  placeholder: string
  value: string
  onChange: (v: string) => void
  icon?: React.ElementType
}) {
  return (
    <div className="relative">
      {Icon && (
        <Icon className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-slate-500" />
      )}
      <input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className={clsx(
          "w-full bg-slate-800 border border-slate-700 rounded-lg py-2 text-xs text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50",
          Icon ? "pl-8 pr-3" : "px-3",
        )}
      />
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="pb-2 px-5 font-medium text-xs first:pl-5">{children}</th>
}
function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={clsx("py-2.5 px-5 text-slate-300 first:pl-5", className)}>{children}</td>
}

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
