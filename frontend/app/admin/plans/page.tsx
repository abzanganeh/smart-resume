"use client"

import { useEffect, useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import { Plus, Pencil, Loader2, ChevronDown, ChevronUp, X } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminPlans,
  createAdminPlan,
  patchAdminPlan,
  getAdminPlansHistory,
} from "@/lib/admin/api"
import type {
  PlanConfig,
  PlanConfigInterval,
  PlanCreatePayload,
  PlanUpdatePayload,
} from "@/lib/admin/types"

const PLAN_CODES = [
  "weekly",
  "monthly_pro",
  "yearly_pro",
  "monthly_plus",
  "yearly_plus",
  "monthly_premium",
  "yearly_premium",
] as const

const INTERVALS: PlanConfigInterval[] = ["day", "week", "month", "year", "one_time"]

function defaultIntervalForCode(code: string): PlanConfigInterval {
  if (code === "weekly") return "week"
  if (code.startsWith("yearly_")) return "year"
  if (code.startsWith("monthly_")) return "month"
  return "month"
}

function formatAmount(cents: number, currency: string): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency || "USD",
  }).format(cents / 100)
}

export default function AdminPlansPage() {
  const router = useRouter()
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [plans, setPlans] = useState<PlanConfig[]>([])
  const [history, setHistory] = useState<PlanConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingPlan, setEditingPlan] = useState<PlanConfig | null>(null)

  useEffect(() => {
    if (!token) return
    void loadData()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [planData, hist] = await Promise.all([
        getAdminPlans(token!),
        getAdminPlansHistory(token!),
      ])
      setPlans(planData)
      setHistory(hist)
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Failed to load plans"
      if (msg === "admin_setup_incomplete") {
        router.replace("/admin/auth?reason=setup_password")
        return
      }
      setError(msg)
    } finally {
      setLoading(false)
    }
  }

  if (!token) return <NotAuthed />
  if (loading) return <PageSpinner />
  if (error) return <PageError msg={error} onRetry={loadData} />

  return (
    <div className="space-y-8 max-w-5xl">
      <PageHeader
        title="Plans & Pricing"
        action={
          <button
            onClick={() => setShowCreateForm(true)}
            className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
          >
            <Plus className="w-4 h-4" />
            New plan version
          </button>
        }
      />

      <Section title="Active Plan Configs">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <Th>Code</Th>
                <Th>Interval</Th>
                <Th>Price</Th>
                <Th>Stripe price ID</Th>
                <Th>Active</Th>
                <Th>Effective from</Th>
                <Th>&nbsp;</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {plans.map((p) => (
                <tr key={p.id} className="hover:bg-slate-800/40 transition-colors">
                  <Td>
                    <span className="font-medium text-white">{p.code}</span>
                  </Td>
                  <Td>
                    <IntervalBadge interval={p.interval} />
                  </Td>
                  <Td>{formatAmount(p.amount_cents, p.currency)}</Td>
                  <Td className="text-xs text-slate-400 font-mono">{p.stripe_price_id}</Td>
                  <Td>
                    {p.is_active ? (
                      <span className="text-emerald-400 text-xs">Active</span>
                    ) : (
                      <span className="text-slate-500 text-xs">Inactive</span>
                    )}
                  </Td>
                  <Td className="text-slate-400 text-xs">
                    {new Date(p.effective_from).toLocaleDateString()}
                  </Td>
                  <Td>
                    {p.is_active && (
                      <button
                        onClick={() => setEditingPlan(p)}
                        className="text-slate-400 hover:text-white transition-colors"
                        title="Edit"
                      >
                        <Pencil className="w-3.5 h-3.5" />
                      </button>
                    )}
                  </Td>
                </tr>
              ))}
              {plans.length === 0 && (
                <tr>
                  <td colSpan={7} className="text-center text-slate-500 py-8">
                    No plan configs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      <Section
        title={`Change History (${history.length})`}
        action={
          <button
            onClick={() => setShowHistory((v) => !v)}
            className="flex items-center gap-1 text-slate-400 hover:text-white text-xs transition-colors"
          >
            {showHistory ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            {showHistory ? "Collapse" : "Expand"}
          </button>
        }
      >
        {showHistory && (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-left text-slate-400 border-b border-slate-800">
                  <Th>Code</Th>
                  <Th>Interval</Th>
                  <Th>Price</Th>
                  <Th>Created</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {history.map((p) => (
                  <tr key={p.id} className="text-slate-400">
                    <Td>{p.code}</Td>
                    <Td>
                      <IntervalBadge interval={p.interval} />
                    </Td>
                    <Td>{formatAmount(p.amount_cents, p.currency)}</Td>
                    <Td className="text-xs">{new Date(p.created_at).toLocaleString()}</Td>
                    <Td>
                      {p.effective_to ? (
                        <span className="text-slate-600 text-xs">Superseded</span>
                      ) : p.is_active ? (
                        <span className="text-emerald-400 text-xs">Active</span>
                      ) : (
                        <span className="text-slate-500 text-xs">Inactive</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {showCreateForm && (
        <PlanCreateModal
          onSave={async (payload) => {
            const res = await createAdminPlan(token, payload)
            showAuditToast(res.audit_log_id)
            setShowCreateForm(false)
            await loadData()
          }}
          onClose={() => setShowCreateForm(false)}
        />
      )}

      {editingPlan && (
        <PlanEditModal
          initial={editingPlan}
          onSave={async (payload) => {
            const res = await patchAdminPlan(token, editingPlan.id, payload)
            showAuditToast(res.audit_log_id)
            setEditingPlan(null)
            await loadData()
          }}
          onClose={() => setEditingPlan(null)}
        />
      )}
    </div>
  )
}

function PlanCreateModal({
  onSave,
  onClose,
}: {
  onSave: (payload: PlanCreatePayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [code, setCode] = useState<string>(PLAN_CODES[1])
  const [interval, setInterval] = useState<PlanConfigInterval>(defaultIntervalForCode(PLAN_CODES[1]))
  const [amountCents, setAmountCents] = useState("")
  const [currency, setCurrency] = useState("USD")
  const [stripePriceId, setStripePriceId] = useState("")
  const [stripeProductId, setStripeProductId] = useState("")
  const [eligibility, setEligibility] = useState("")

  function handleCodeChange(next: string) {
    setCode(next)
    setInterval(defaultIntervalForCode(next))
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave({
          code,
          stripe_price_id: stripePriceId,
          stripe_product_id: stripeProductId || null,
          eligibility: eligibility || undefined,
          amount_cents: parseInt(amountCents, 10),
          currency,
          interval,
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title="New Plan Version" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}
        <FormField label="Plan code">
          <select value={code} onChange={(e) => handleCodeChange(e.target.value)} className={inputCls}>
            {PLAN_CODES.map((c) => (
              <option key={c} value={c}>
                {c}
              </option>
            ))}
          </select>
        </FormField>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Interval">
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as PlanConfigInterval)}
              className={inputCls}
            >
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Currency">
            <input value={currency} onChange={(e) => setCurrency(e.target.value)} className={inputCls} />
          </FormField>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Amount (cents)">
            <input
              type="number"
              min="0"
              required
              value={amountCents}
              onChange={(e) => setAmountCents(e.target.value)}
              className={inputCls}
              placeholder="1999"
            />
          </FormField>
          <FormField label="Stripe price ID">
            <input
              type="text"
              required
              value={stripePriceId}
              onChange={(e) => setStripePriceId(e.target.value)}
              className={inputCls}
              placeholder="price_..."
            />
          </FormField>
        </div>
        <FormField label="Stripe product ID (optional)">
          <input
            type="text"
            value={stripeProductId}
            onChange={(e) => setStripeProductId(e.target.value)}
            className={inputCls}
            placeholder="prod_..."
          />
        </FormField>
        <FormField label="Eligibility note (optional)">
          <input
            type="text"
            value={eligibility}
            onChange={(e) => setEligibility(e.target.value)}
            className={inputCls}
          />
        </FormField>
        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Create plan" />
      </form>
    </Modal>
  )
}

function PlanEditModal({
  initial,
  onSave,
  onClose,
}: {
  initial: PlanConfig
  onSave: (payload: PlanUpdatePayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [interval, setInterval] = useState<PlanConfigInterval>(initial.interval)
  const [amountCents, setAmountCents] = useState(String(initial.amount_cents))
  const [currency, setCurrency] = useState(initial.currency)
  const [stripePriceId, setStripePriceId] = useState(initial.stripe_price_id)
  const [stripeProductId, setStripeProductId] = useState(initial.stripe_product_id ?? "")
  const [eligibility, setEligibility] = useState(initial.eligibility)
  const [isActive, setIsActive] = useState(initial.is_active)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    startTransition(async () => {
      try {
        await onSave({
          stripe_price_id: stripePriceId,
          stripe_product_id: stripeProductId || null,
          eligibility,
          amount_cents: parseInt(amountCents, 10),
          currency,
          interval,
          is_active: isActive,
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title={`Edit ${initial.code}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}
        <p className="text-xs text-slate-500">
          Plan code <span className="text-slate-300">{initial.code}</span> cannot be changed — create a new version instead.
        </p>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Interval">
            <select
              value={interval}
              onChange={(e) => setInterval(e.target.value as PlanConfigInterval)}
              className={inputCls}
            >
              {INTERVALS.map((i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </FormField>
          <FormField label="Currency">
            <input value={currency} onChange={(e) => setCurrency(e.target.value)} className={inputCls} />
          </FormField>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <FormField label="Amount (cents)">
            <input
              type="number"
              min="0"
              required
              value={amountCents}
              onChange={(e) => setAmountCents(e.target.value)}
              className={inputCls}
            />
          </FormField>
          <FormField label="Stripe price ID">
            <input
              type="text"
              required
              value={stripePriceId}
              onChange={(e) => setStripePriceId(e.target.value)}
              className={inputCls}
            />
          </FormField>
        </div>
        <FormField label="Stripe product ID">
          <input
            type="text"
            value={stripeProductId}
            onChange={(e) => setStripeProductId(e.target.value)}
            className={inputCls}
          />
        </FormField>
        <FormField label="Eligibility">
          <input value={eligibility} onChange={(e) => setEligibility(e.target.value)} className={inputCls} />
        </FormField>
        <label className="flex items-center gap-2 text-sm text-slate-300">
          <input
            type="checkbox"
            checked={isActive}
            onChange={(e) => setIsActive(e.target.checked)}
            className="accent-amber-500"
          />
          Active
        </label>
        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Save changes" />
      </form>
    </Modal>
  )
}

const inputCls =
  "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

function PageHeader({ title, action }: { title: string; action?: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between">
      <h1 className="text-xl font-semibold text-white">{title}</h1>
      {action}
    </div>
  )
}

function Section({
  title,
  action,
  children,
}: {
  title: string
  action?: React.ReactNode
  children: React.ReactNode
}) {
  return (
    <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-slate-800">
        <h2 className="text-sm font-medium text-slate-200">{title}</h2>
        {action}
      </div>
      <div className="p-5">{children}</div>
    </div>
  )
}

function Th({ children }: { children: React.ReactNode }) {
  return <th className="pb-2 pr-4 font-medium text-xs">{children}</th>
}

function Td({ children, className }: { children: React.ReactNode; className?: string }) {
  return <td className={clsx("py-2.5 pr-4 text-slate-300", className)}>{children}</td>
}

function IntervalBadge({ interval }: { interval: string }) {
  return (
    <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-300">{interval}</span>
  )
}

function Modal({
  title,
  children,
  onClose,
}: {
  title: string
  children: React.ReactNode
  onClose: () => void
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="font-medium text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <div className="p-5">{children}</div>
      </div>
    </div>
  )
}

function FormField({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div>
      <label className="block text-xs text-slate-400 mb-1.5">{label}</label>
      {children}
    </div>
  )
}

function ModalActions({
  onClose,
  isPending,
  submitLabel,
}: {
  onClose: () => void
  isPending: boolean
  submitLabel: string
}) {
  return (
    <div className="flex gap-3 pt-2 justify-end">
      <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">
        Cancel
      </button>
      <button
        type="submit"
        disabled={isPending}
        className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
      >
        {isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {submitLabel}
      </button>
    </div>
  )
}

function ErrorBanner({ msg }: { msg: string }) {
  return (
    <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
      {msg}
    </div>
  )
}

function PageSpinner() {
  return (
    <div className="flex items-center justify-center h-64">
      <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
    </div>
  )
}

function PageError({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 h-64 justify-center text-center">
      <p className="text-red-400">{msg}</p>
      <button onClick={onRetry} className="text-sm text-amber-400 hover:underline">
        Retry
      </button>
    </div>
  )
}

function NotAuthed() {
  return (
    <div className="flex items-center justify-center h-64 text-slate-400 text-sm">
      Not authenticated.
    </div>
  )
}
