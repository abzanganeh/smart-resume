"use client"

import { useEffect, useState, useCallback } from "react"
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
  FunnelChart,
  Funnel,
  Cell,
  LabelList,
} from "recharts"
import { Download, Loader2 } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession } from "@/app/admin/layout"
import {
  getActivityMetrics,
  getFunnelMetrics,
  getRevenueByPlan,
  getLLMCostMargin,
  getChurnMetrics,
  exportReportCSV,
} from "@/lib/admin/api"
import type {
  ActivityMetrics,
  FunnelMetrics,
  RevenueByPlan,
  LLMCostMargin,
  ChurnMetrics,
} from "@/lib/admin/types"

type ReportTab = "activity" | "funnel" | "revenue" | "llm_cost" | "churn"

const TABS: Array<{ id: ReportTab; label: string }> = [
  { id: "activity", label: "DAU/WAU/MAU" },
  { id: "funnel", label: "Registration Funnel" },
  { id: "revenue", label: "Revenue by Plan" },
  { id: "llm_cost", label: "LLM Cost vs Margin" },
  { id: "churn", label: "Churn" },
]

// ── Chart color palette matching dark UI ─────────────────────────────────────

const COLORS = {
  amber: "#F59E0B",
  emerald: "#10B981",
  blue: "#3B82F6",
  violet: "#8B5CF6",
  red: "#EF4444",
  slate: "#94A3B8",
}

// ── Reports Page ──────────────────────────────────────────────────────────────

export default function AdminReportsPage() {
  const { token } = useAdminSession()

  const [tab, setTab] = useState<ReportTab>("activity")

  // Date range — default last 30 days
  const today = new Date().toISOString().slice(0, 10)
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
  const [from, setFrom] = useState(thirtyDaysAgo)
  const [to, setTo] = useState(today)

  const dateParams = { from, to }

  if (!token) return <NotAuthed />

  return (
    <div className="space-y-6 max-w-6xl">
      <div className="flex items-center justify-between flex-wrap gap-3">
        <h1 className="text-xl font-semibold text-white">Reports</h1>

        {/* Date range */}
        <div className="flex items-center gap-2 text-sm">
          <input
            type="date"
            value={from}
            max={to}
            onChange={(e) => setFrom(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
          />
          <span className="text-slate-500">→</span>
          <input
            type="date"
            value={to}
            min={from}
            max={today}
            onChange={(e) => setTo(e.target.value)}
            className="bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-white text-sm focus:outline-none focus:ring-2 focus:ring-amber-500/50"
          />
          <ExportButton token={token} tab={tab} dateParams={dateParams} />
        </div>
      </div>

      {/* Tabs */}
      <div className="flex flex-wrap gap-1 bg-slate-900 border border-slate-800 rounded-xl p-1">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={clsx(
              "px-4 py-2 rounded-lg text-sm transition-colors",
              tab === t.id
                ? "bg-amber-600 text-white font-medium"
                : "text-slate-400 hover:text-slate-200",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Chart area */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl p-6 min-h-96">
        {tab === "activity" && <ActivityChart token={token} dateParams={dateParams} />}
        {tab === "funnel" && <FunnelChartView token={token} dateParams={dateParams} />}
        {tab === "revenue" && <RevenueChart token={token} dateParams={dateParams} />}
        {tab === "llm_cost" && <LLMCostChart token={token} dateParams={dateParams} />}
        {tab === "churn" && <ChurnChart token={token} dateParams={dateParams} />}
      </div>
    </div>
  )
}

// ── Export button ─────────────────────────────────────────────────────────────

function ExportButton({
  token,
  tab,
  dateParams,
}: {
  token: string
  tab: ReportTab
  dateParams: { from: string; to: string }
}) {
  const [exporting, setExporting] = useState(false)

  async function handleExport() {
    setExporting(true)
    try {
      const blob = await exportReportCSV(token, tab, dateParams)
      const url = URL.createObjectURL(blob)
      const a = document.createElement("a")
      a.href = url
      a.download = `admin-report-${tab}-${dateParams.from}-${dateParams.to}.csv`
      a.click()
      URL.revokeObjectURL(url)
    } finally {
      setExporting(false)
    }
  }

  return (
    <button
      onClick={handleExport}
      disabled={exporting}
      className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-50 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
    >
      {exporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
      Export CSV
    </button>
  )
}

// ── Activity Chart ────────────────────────────────────────────────────────────

function ActivityChart({
  token,
  dateParams,
}: {
  token: string
  dateParams: { from: string; to: string }
}) {
  const [data, setData] = useState<ActivityMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getActivityMetrics(token, dateParams)
      .then((r) => setData(r.metrics))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, dateParams.from, dateParams.to]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <ChartSpinner />
  if (error) return <ChartError msg={error} />

  return (
    <>
      <h2 className="text-sm font-medium text-slate-200 mb-5">Daily / Weekly / Monthly Active Users</h2>
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
          <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} labelStyle={{ color: "#f1f5f9" }} itemStyle={{ color: "#94a3b8" }} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          <Line type="monotone" dataKey="dau" name="DAU" stroke={COLORS.amber} dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="wau" name="WAU" stroke={COLORS.blue} dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="mau" name="MAU" stroke={COLORS.emerald} dot={false} strokeWidth={2} />
          <Line type="monotone" dataKey="new_registrations" name="Registrations" stroke={COLORS.violet} dot={false} strokeWidth={1.5} strokeDasharray="4 2" />
        </LineChart>
      </ResponsiveContainer>
    </>
  )
}

// ── Funnel Chart ──────────────────────────────────────────────────────────────

function FunnelChartView({
  token,
  dateParams,
}: {
  token: string
  dateParams: { from: string; to: string }
}) {
  const [data, setData] = useState<FunnelMetrics | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getFunnelMetrics(token, dateParams)
      .then(setData)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, dateParams.from, dateParams.to]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <ChartSpinner />
  if (error) return <ChartError msg={error} />
  if (!data) return null

  const funnelData = [
    { name: "Registered", value: data.registered, fill: COLORS.amber },
    { name: "Email verified", value: data.email_verified, fill: COLORS.blue },
    { name: "First build", value: data.first_build, fill: COLORS.emerald },
    { name: "First export", value: data.first_export, fill: COLORS.violet },
    { name: "Subscribed", value: data.subscribed, fill: COLORS.red },
  ]

  return (
    <>
      <h2 className="text-sm font-medium text-slate-200 mb-5">Registration Funnel</h2>
      <ResponsiveContainer width="100%" height={350}>
        <FunnelChart>
          <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} itemStyle={{ color: "#94a3b8" }} />
          <Funnel dataKey="value" data={funnelData} isAnimationActive>
            {funnelData.map((entry, index) => (
              <Cell key={`cell-${index}`} fill={entry.fill} />
            ))}
            <LabelList dataKey="name" position="right" fill="#94a3b8" fontSize={12} />
          </Funnel>
        </FunnelChart>
      </ResponsiveContainer>
    </>
  )
}

// ── Revenue Chart ─────────────────────────────────────────────────────────────

function RevenueChart({
  token,
  dateParams,
}: {
  token: string
  dateParams: { from: string; to: string }
}) {
  const [data, setData] = useState<RevenueByPlan[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getRevenueByPlan(token, dateParams)
      .then((r) => setData(r.revenue))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, dateParams.from, dateParams.to]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <ChartSpinner />
  if (error) return <ChartError msg={error} />

  return (
    <>
      <h2 className="text-sm font-medium text-slate-200 mb-5">Revenue by Plan (USD)</h2>
      <ResponsiveContainer width="100%" height={350}>
        <BarChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="plan" tick={{ fill: "#64748b", fontSize: 12 }} />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
          <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} labelStyle={{ color: "#f1f5f9" }} itemStyle={{ color: "#94a3b8" }} formatter={(v) => [`$${Number(v).toFixed(2)}`, "Revenue"]} />
          <Bar dataKey="revenue_usd" name="Revenue (USD)" fill={COLORS.amber} radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
      {/* Subscribers */}
      <div className="mt-4 flex flex-wrap gap-4">
        {data.map((d) => (
          <div key={d.plan} className="text-xs text-slate-400">
            <span className="capitalize font-medium text-slate-300">{d.plan}</span>: {d.subscribers} subscribers · ${d.revenue_usd.toFixed(2)}
          </div>
        ))}
      </div>
    </>
  )
}

// ── LLM Cost vs Margin Chart ──────────────────────────────────────────────────

function LLMCostChart({
  token,
  dateParams,
}: {
  token: string
  dateParams: { from: string; to: string }
}) {
  const [data, setData] = useState<LLMCostMargin[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [tierFilter, setTierFilter] = useState<"standard" | "better" | "best" | "all">("all")

  useEffect(() => {
    setLoading(true)
    setError(null)
    getLLMCostMargin(token, dateParams)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, dateParams.from, dateParams.to]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <ChartSpinner />
  if (error) return <ChartError msg={error} />

  const filtered = tierFilter === "all" ? data : data.filter((d) => d.tier === tierFilter)

  return (
    <>
      <div className="flex items-center justify-between mb-5">
        <h2 className="text-sm font-medium text-slate-200">LLM Cost vs Revenue Margin</h2>
        <div className="flex gap-1">
          {(["all", "standard", "better", "best"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTierFilter(t)}
              className={clsx(
                "px-2.5 py-1 rounded text-xs capitalize transition-colors",
                tierFilter === t ? "bg-amber-600 text-white" : "bg-slate-700 text-slate-400 hover:bg-slate-600",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>
      <ResponsiveContainer width="100%" height={320}>
        <BarChart data={filtered} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} />
          <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} labelStyle={{ color: "#f1f5f9" }} itemStyle={{ color: "#94a3b8" }} formatter={(v) => `$${Number(v).toFixed(4)}`} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          <Bar dataKey="cost_usd" name="Cost" fill={COLORS.red} radius={[2, 2, 0, 0]} />
          <Bar dataKey="revenue_usd" name="Revenue" fill={COLORS.emerald} radius={[2, 2, 0, 0]} />
          <Bar dataKey="margin_usd" name="Margin" fill={COLORS.amber} radius={[2, 2, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </>
  )
}

// ── Churn Chart ───────────────────────────────────────────────────────────────

function ChurnChart({
  token,
  dateParams,
}: {
  token: string
  dateParams: { from: string; to: string }
}) {
  const [data, setData] = useState<ChurnMetrics[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    setLoading(true)
    setError(null)
    getChurnMetrics(token, dateParams)
      .then((r) => setData(r.data))
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [token, dateParams.from, dateParams.to]) // eslint-disable-line react-hooks/exhaustive-deps

  if (loading) return <ChartSpinner />
  if (error) return <ChartError msg={error} />

  return (
    <>
      <h2 className="text-sm font-medium text-slate-200 mb-5">Churn Rate by Plan</h2>
      <ResponsiveContainer width="100%" height={350}>
        <LineChart data={data} margin={{ top: 5, right: 20, bottom: 5, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
          <XAxis dataKey="date" tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(d) => d.slice(5)} />
          <YAxis tick={{ fill: "#64748b", fontSize: 11 }} tickFormatter={(v) => `${(v * 100).toFixed(1)}%`} />
          <Tooltip contentStyle={{ backgroundColor: "#0f172a", border: "1px solid #1e293b", borderRadius: 8 }} labelStyle={{ color: "#f1f5f9" }} itemStyle={{ color: "#94a3b8" }} formatter={(v) => [`${(Number(v) * 100).toFixed(2)}%`, "Churn"]} />
          <Legend wrapperStyle={{ fontSize: 12, color: "#94a3b8" }} />
          <Line type="monotone" dataKey="churn_rate" name="Churn rate" stroke={COLORS.red} dot={false} strokeWidth={2} />
        </LineChart>
      </ResponsiveContainer>
    </>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function ChartSpinner() {
  return (
    <div className="flex items-center justify-center h-80">
      <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
    </div>
  )
}

function ChartError({ msg }: { msg: string }) {
  return (
    <div className="flex items-center justify-center h-80 text-red-400 text-sm">
      {msg}
    </div>
  )
}

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
