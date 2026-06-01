"use client"

import { useEffect, useState, useTransition } from "react"
import { Loader2, CheckCircle, XCircle, X } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import { getAdminRefunds, approveRefund, denyRefund } from "@/lib/admin/api"
import type { RefundRequest } from "@/lib/admin/types"

// ── Refunds Page ──────────────────────────────────────────────────────────────

export default function AdminRefundsPage() {
  const { token, session } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [refunds, setRefunds] = useState<RefundRequest[]>([])
  const [total, setTotal] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [statusFilter, setStatusFilter] = useState<"pending" | "approved" | "denied">("pending")
  const [denyingId, setDenyingId] = useState<string | null>(null)
  const [denyReason, setDenyReason] = useState("")
  const [actionError, setActionError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()

  const isSuperAdmin = session?.admin.role === "super-admin"

  useEffect(() => {
    if (!token) return
    loadRefunds()
  }, [token, statusFilter]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadRefunds() {
    setLoading(true)
    setError(null)
    try {
      const res = await getAdminRefunds(token!, statusFilter)
      setRefunds(res.refunds)
      setTotal(res.total)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load refunds")
    } finally {
      setLoading(false)
    }
  }

  function handleApprove(id: string) {
    if (!isSuperAdmin) return
    setActionError(null)
    startTransition(async () => {
      try {
        const res = await approveRefund(token!, id)
        showAuditToast(res.audit_log_id)
        setRefunds((prev) => prev.filter((r) => r.id !== id))
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Approve failed")
      }
    })
  }

  function handleDenySubmit() {
    if (!denyingId || !denyReason) return
    setActionError(null)
    startTransition(async () => {
      try {
        const res = await denyRefund(token!, denyingId, denyReason)
        showAuditToast(res.audit_log_id)
        setRefunds((prev) => prev.filter((r) => r.id !== denyingId))
        setDenyingId(null)
        setDenyReason("")
      } catch (e) {
        setActionError(e instanceof Error ? e.message : "Deny failed")
      }
    })
  }

  if (!token) return <NotAuthed />

  return (
    <div className="space-y-5 max-w-5xl">
      <h1 className="text-xl font-semibold text-white">Refund Requests</h1>

      {/* Status filter */}
      <div className="flex gap-2">
        {(["pending", "approved", "denied"] as const).map((s) => (
          <button
            key={s}
            onClick={() => setStatusFilter(s)}
            className={clsx(
              "px-4 py-1.5 rounded-lg text-sm capitalize transition-colors",
              statusFilter === s
                ? "bg-amber-600 text-white"
                : "bg-slate-800 text-slate-400 hover:bg-slate-700",
            )}
          >
            {s}
          </button>
        ))}
      </div>

      {error && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {error}
        </div>
      )}

      {actionError && (
        <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
          {actionError}
        </div>
      )}

      {/* Table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-medium text-slate-200 capitalize">{statusFilter} refunds ({total})</h2>
        </div>

        {loading ? (
          <div className="flex items-center justify-center py-16">
            <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
          </div>
        ) : refunds.length === 0 ? (
          <div className="text-center text-slate-500 py-12 text-sm">
            No {statusFilter} refunds.
          </div>
        ) : (
          <div className="divide-y divide-slate-800">
            {refunds.map((r) => (
              <RefundRow
                key={r.id}
                refund={r}
                isSuperAdmin={isSuperAdmin}
                isPending={isPending}
                onApprove={() => handleApprove(r.id)}
                onDeny={() => {
                  setDenyingId(r.id)
                  setDenyReason("")
                }}
              />
            ))}
          </div>
        )}
      </div>

      {/* Deny confirmation modal */}
      {denyingId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md p-5 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="font-medium text-white">Deny Refund</h3>
              <button onClick={() => setDenyingId(null)} className="text-slate-500 hover:text-white">
                <X className="w-4 h-4" />
              </button>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Reason (sent to user via email)</label>
              <textarea
                rows={3}
                value={denyReason}
                onChange={(e) => setDenyReason(e.target.value)}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none"
                placeholder="The charge occurred more than 7 days ago and is outside our refund window."
              />
            </div>
            <div className="flex gap-3 justify-end">
              <button
                onClick={() => setDenyingId(null)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors"
              >
                Cancel
              </button>
              <button
                disabled={!denyReason || isPending}
                onClick={handleDenySubmit}
                className="flex items-center gap-2 bg-red-700 hover:bg-red-600 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
              >
                {isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                Deny refund
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Refund Row ────────────────────────────────────────────────────────────────

function RefundRow({
  refund,
  isSuperAdmin,
  isPending,
  onApprove,
  onDeny,
}: {
  refund: RefundRequest
  isSuperAdmin: boolean
  isPending: boolean
  onApprove: () => void
  onDeny: () => void
}) {
  return (
    <div className="px-5 py-4 flex items-start gap-4">
      <div className="flex-1 space-y-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <p className="text-sm text-white font-medium truncate">{refund.user_email}</p>
          <StatusBadge status={refund.status} />
        </div>
        <p className="text-sm text-amber-300 font-semibold">${refund.amount_usd.toFixed(2)}</p>
        <p className="text-xs text-slate-400 line-clamp-2">{refund.reason}</p>
        <div className="flex items-center gap-3 text-xs text-slate-500">
          <span>Requested {new Date(refund.created_at).toLocaleDateString()}</span>
          {refund.stripe_charge_id && (
            <code className="text-slate-600">{refund.stripe_charge_id.slice(0, 16)}…</code>
          )}
        </div>
        {refund.deny_reason && (
          <p className="text-xs text-red-400 mt-1">Denied: {refund.deny_reason}</p>
        )}
      </div>

      {refund.status === "pending" && isSuperAdmin && (
        <div className="flex items-center gap-2 shrink-0">
          <button
            disabled={isPending}
            onClick={onApprove}
            className="flex items-center gap-1.5 bg-emerald-700 hover:bg-emerald-600 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
            title="Approve refund"
          >
            <CheckCircle className="w-3.5 h-3.5" />
            Approve
          </button>
          <button
            disabled={isPending}
            onClick={onDeny}
            className="flex items-center gap-1.5 bg-red-800 hover:bg-red-700 disabled:opacity-40 text-white text-xs px-3 py-1.5 rounded-lg transition-colors"
            title="Deny refund"
          >
            <XCircle className="w-3.5 h-3.5" />
            Deny
          </button>
        </div>
      )}
    </div>
  )
}

// ── Status badge ──────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status: RefundRequest["status"] }) {
  const styles: Record<RefundRequest["status"], string> = {
    pending: "bg-amber-900/40 text-amber-300 border-amber-700/40",
    approved: "bg-emerald-900/40 text-emerald-300 border-emerald-700/40",
    denied: "bg-red-900/40 text-red-300 border-red-700/40",
  }
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full border capitalize", styles[status])}>
      {status}
    </span>
  )
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
