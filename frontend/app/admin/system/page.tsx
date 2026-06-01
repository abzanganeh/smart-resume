"use client"

import { useEffect, useState } from "react"
import { Loader2, RefreshCw, AlertTriangle, CheckCircle, ZapOff } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession } from "@/app/admin/layout"
import { getSystemHealth } from "@/lib/admin/api"
import type { SystemHealth, LatencyPercentiles } from "@/lib/admin/types"

// ── System Health Page ────────────────────────────────────────────────────────

export default function AdminSystemPage() {
  const { token } = useAdminSession()
  const [health, setHealth] = useState<SystemHealth | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [refreshing, setRefreshing] = useState(false)
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null)

  useEffect(() => {
    if (!token) return
    loadHealth()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadHealth() {
    setLoading(true)
    setError(null)
    try {
      const res = await getSystemHealth(token!)
      setHealth(res)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load system health")
    } finally {
      setLoading(false)
    }
  }

  async function handleRefresh() {
    setRefreshing(true)
    try {
      const res = await getSystemHealth(token!)
      setHealth(res)
      setLastUpdated(new Date())
    } catch (e) {
      setError(e instanceof Error ? e.message : "Refresh failed")
    } finally {
      setRefreshing(false)
    }
  }

  if (!token) return <NotAuthed />

  return (
    <div className="space-y-6 max-w-5xl">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-white">System Health</h1>
          {lastUpdated && (
            <p className="text-xs text-slate-500 mt-0.5">
              Last updated: {lastUpdated.toLocaleTimeString()}
            </p>
          )}
        </div>
        <button
          onClick={handleRefresh}
          disabled={refreshing || loading}
          className="flex items-center gap-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
        >
          <RefreshCw className={clsx("w-3.5 h-3.5", (refreshing || loading) && "animate-spin")} />
          Refresh
        </button>
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {loading && !health && (
        <div className="flex items-center justify-center h-64">
          <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
        </div>
      )}

      {health && (
        <>
          {/* Top-level indicators */}
          <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
            <HealthCard
              title="Stripe Webhooks"
              value={`${(health.stripe_webhook_success_rate * 100).toFixed(1)}%`}
              sub="Success rate"
              status={health.stripe_webhook_success_rate >= 0.99 ? "ok" : health.stripe_webhook_success_rate >= 0.95 ? "warn" : "error"}
            />
            <HealthCard
              title="Hirebase CB"
              value={health.hirebase_circuit_breaker}
              sub="Circuit breaker state"
              status={
                health.hirebase_circuit_breaker === "closed" ? "ok" :
                health.hirebase_circuit_breaker === "half-open" ? "warn" : "error"
              }
            />
            <HealthCard
              title="Apify Queue"
              value={String(health.apify_queue_depth)}
              sub="Jobs queued"
              status={health.apify_queue_depth < 100 ? "ok" : health.apify_queue_depth < 500 ? "warn" : "error"}
            />
            <HealthCard
              title="Resend Delivery"
              value={`${(health.resend_delivery_success_rate * 100).toFixed(1)}%`}
              sub="Email delivery"
              status={health.resend_delivery_success_rate >= 0.98 ? "ok" : health.resend_delivery_success_rate >= 0.9 ? "warn" : "error"}
            />
            <HealthCard
              title="Error Rate (24h)"
              value={`${(health.error_rate_24h * 100).toFixed(2)}%`}
              sub="Backend errors"
              status={health.error_rate_24h < 0.01 ? "ok" : health.error_rate_24h < 0.05 ? "warn" : "error"}
            />
          </div>

          {/* LLM latency percentiles */}
          <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
            <div className="px-5 py-3 border-b border-slate-800">
              <h2 className="text-sm font-medium text-slate-200">LLM Latency Percentiles</h2>
            </div>
            <div className="p-5">
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="text-left text-slate-400 border-b border-slate-800">
                      <th className="pb-2 pr-6 text-xs font-medium">Tier</th>
                      <th className="pb-2 pr-6 text-xs font-medium">p50</th>
                      <th className="pb-2 pr-6 text-xs font-medium">p95</th>
                      <th className="pb-2 text-xs font-medium">p99</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800">
                    {(["standard", "better", "best"] as const).map((tier) => (
                      <LatencyRow
                        key={tier}
                        tier={tier}
                        percentiles={health.llm_latency[tier]}
                      />
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  )
}

// ── Health Card ───────────────────────────────────────────────────────────────

function HealthCard({
  title,
  value,
  sub,
  status,
}: {
  title: string
  value: string
  sub: string
  status: "ok" | "warn" | "error"
}) {
  const styles = {
    ok: { border: "border-emerald-700/40", bg: "bg-emerald-900/20", icon: CheckCircle, iconColor: "text-emerald-400" },
    warn: { border: "border-amber-700/40", bg: "bg-amber-900/20", icon: AlertTriangle, iconColor: "text-amber-400" },
    error: { border: "border-red-700/40", bg: "bg-red-900/20", icon: ZapOff, iconColor: "text-red-400" },
  }[status]

  const Icon = styles.icon

  return (
    <div className={clsx("border rounded-xl p-4 space-y-2", styles.bg, styles.border)}>
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400">{title}</span>
        <Icon className={clsx("w-4 h-4", styles.iconColor)} />
      </div>
      <p className="text-xl font-semibold text-white capitalize">{value}</p>
      <p className="text-xs text-slate-500">{sub}</p>
    </div>
  )
}

// ── Latency Row ───────────────────────────────────────────────────────────────

function LatencyRow({ tier, percentiles }: { tier: string; percentiles: LatencyPercentiles }) {
  const tierColors: Record<string, string> = {
    standard: "bg-slate-700 text-slate-200",
    better: "bg-amber-900/60 text-amber-300",
    best: "bg-violet-900/60 text-violet-300",
  }

  function latencyColor(ms: number): string {
    if (ms < 2000) return "text-emerald-400"
    if (ms < 5000) return "text-amber-400"
    return "text-red-400"
  }

  return (
    <tr>
      <td className="py-2.5 pr-6">
        <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium capitalize", tierColors[tier] ?? tierColors.standard)}>
          {tier}
        </span>
      </td>
      <td className={clsx("py-2.5 pr-6 font-mono text-sm", latencyColor(percentiles.p50))}>
        {percentiles.p50.toFixed(0)}ms
      </td>
      <td className={clsx("py-2.5 pr-6 font-mono text-sm", latencyColor(percentiles.p95))}>
        {percentiles.p95.toFixed(0)}ms
      </td>
      <td className={clsx("py-2.5 font-mono text-sm", latencyColor(percentiles.p99))}>
        {percentiles.p99.toFixed(0)}ms
      </td>
    </tr>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
