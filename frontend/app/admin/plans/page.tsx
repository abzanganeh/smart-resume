"use client"

import { useEffect, useState, useTransition } from "react"
import { useRouter } from "next/navigation"
import { Plus, Pencil, Check, X, Loader2, ChevronDown, ChevronUp } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminPlans,
  createAdminPlan,
  patchAdminPlan,
  getAdminPlansHistory,
  updateAdminAddonPricing,
} from "@/lib/admin/api"
import type { PlanConfig, PlanCreatePayload, LLMAddonPricing } from "@/lib/admin/types"

// ── Plans Page ────────────────────────────────────────────────────────────────

export default function AdminPlansPage() {
  const router = useRouter()
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [plans, setPlans] = useState<PlanConfig[]>([])
  const [addon, setAddon] = useState<LLMAddonPricing | null>(null)
  const [history, setHistory] = useState<PlanConfig[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [showCreateForm, setShowCreateForm] = useState(false)
  const [editingPlan, setEditingPlan] = useState<PlanConfig | null>(null)
  const [editingAddon, setEditingAddon] = useState(false)

  useEffect(() => {
    if (!token) return
    loadData()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [planData, hist] = await Promise.all([
        getAdminPlans(token!),
        getAdminPlansHistory(token!),
      ])
      setPlans(planData.plans ?? [])
      setAddon(planData.addon_pricing ?? null)
      setHistory(Array.isArray(hist) ? hist : [])
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

      {/* ── Active plans table ───────────────────────────────────────── */}
      <Section title="Current Plan Configs">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <Th>Plan</Th>
                <Th>Cycle</Th>
                <Th>Price (USD)</Th>
                <Th>Resumes</Th>
                <Th>Searches</Th>
                <Th>Trial days</Th>
                <Th>Effective from</Th>
                <Th>Apply to existing</Th>
                <Th>&nbsp;</Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {plans.map((p) => (
                <tr key={p.id} className="hover:bg-slate-800/40 transition-colors">
                  <Td>
                    <span className="capitalize font-medium text-white">{p.plan}</span>
                  </Td>
                  <Td>
                    <CycleBadge cycle={p.billing_cycle} />
                  </Td>
                  <Td>${p.price_usd.toFixed(2)}</Td>
                  <Td>{p.resume_limit}</Td>
                  <Td>{p.search_limit}</Td>
                  <Td>
                    {p.trial_days > 0 ? (
                      <span className="text-emerald-400">{p.trial_days}d</span>
                    ) : (
                      <span className="text-slate-500">—</span>
                    )}
                  </Td>
                  <Td className="text-slate-400 text-xs">
                    {new Date(p.effective_from).toLocaleDateString()}
                  </Td>
                  <Td>
                    {p.apply_to_existing ? (
                      <span className="text-amber-400 text-xs">All at renewal</span>
                    ) : (
                      <span className="text-slate-400 text-xs">New only</span>
                    )}
                  </Td>
                  <Td>
                    {!p.superseded_by && (
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
                  <td colSpan={9} className="text-center text-slate-500 py-8">
                    No plan configs yet.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── LLM add-on pricing ───────────────────────────────────────── */}
      {addon && (
        <Section
          title="LLM Add-on Pricing"
          action={
            <button
              onClick={() => setEditingAddon(true)}
              className="flex items-center gap-1.5 text-slate-400 hover:text-white text-xs transition-colors"
            >
              <Pencil className="w-3 h-3" />
              Edit
            </button>
          }
        >
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-4">
            {[
              { label: "Better 5-pack", value: addon.better_pack_usd },
              { label: "Better monthly", value: addon.better_monthly_usd },
              { label: "Better yearly", value: addon.better_yearly_usd },
              { label: "Best per-resume", value: addon.best_per_resume_usd },
              { label: "Best monthly", value: addon.best_monthly_usd },
              { label: "Best yearly", value: addon.best_yearly_usd },
            ].map(({ label, value }) => (
              <div key={label} className="bg-slate-800/50 rounded-lg p-3">
                <p className="text-xs text-slate-400 mb-1">{label}</p>
                <p className="text-lg font-semibold text-white">${value.toFixed(2)}</p>
              </div>
            ))}
            <div className="bg-slate-800/50 rounded-lg p-3">
              <p className="text-xs text-slate-400 mb-1">Free credit grant</p>
              <p className="text-lg font-semibold text-white">{addon.free_credit_grant}</p>
            </div>
          </div>
        </Section>
      )}

      {/* ── Change history ───────────────────────────────────────────── */}
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
                  <Th>Plan</Th>
                  <Th>Cycle</Th>
                  <Th>Price</Th>
                  <Th>Created</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {history.map((p) => (
                  <tr key={p.id} className="text-slate-400">
                    <Td className="capitalize">{p.plan}</Td>
                    <Td><CycleBadge cycle={p.billing_cycle} /></Td>
                    <Td>${p.price_usd.toFixed(2)}</Td>
                    <Td className="text-xs">{new Date(p.created_at).toLocaleString()}</Td>
                    <Td>
                      {p.superseded_by ? (
                        <span className="text-slate-600 text-xs">Superseded</span>
                      ) : (
                        <span className="text-emerald-400 text-xs">Active</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── Create form modal ────────────────────────────────────────── */}
      {showCreateForm && (
        <PlanFormModal
          title="New Plan Version"
          token={token}
          onSave={async (payload) => {
            const res = await createAdminPlan(token, payload)
            showAuditToast(res.audit_log_id)
            setShowCreateForm(false)
            await loadData()
          }}
          onClose={() => setShowCreateForm(false)}
        />
      )}

      {/* ── Edit form modal ──────────────────────────────────────────── */}
      {editingPlan && (
        <PlanFormModal
          title="Edit Plan Config"
          initial={editingPlan}
          token={token}
          onSave={async (payload) => {
            const res = await patchAdminPlan(token, editingPlan.id, payload)
            showAuditToast(res.audit_log_id)
            setEditingPlan(null)
            await loadData()
          }}
          onClose={() => setEditingPlan(null)}
        />
      )}

      {/* ── Edit add-on pricing modal ─────────────────────────────── */}
      {editingAddon && addon && (
        <AddonPricingModal
          initial={addon}
          token={token}
          onSave={async (payload) => {
            const res = await updateAdminAddonPricing(token, payload)
            showAuditToast(res.audit_log_id)
            setAddon((prev) => (prev ? { ...prev, ...payload } : prev))
            setEditingAddon(false)
          }}
          onClose={() => setEditingAddon(false)}
        />
      )}
    </div>
  )
}

// ── Plan Form Modal ───────────────────────────────────────────────────────────

function PlanFormModal({
  title,
  initial,
  token: _token,
  onSave,
  onClose,
}: {
  title: string
  initial?: PlanConfig
  token: string
  onSave: (payload: PlanCreatePayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)

  const [plan, setPlan] = useState<"daily" | "weekly" | "monthly">(initial?.plan ?? "monthly")
  const [cycle, setCycle] = useState<"recurring" | "yearly">(initial?.billing_cycle ?? "recurring")
  const [price, setPrice] = useState(String(initial?.price_usd ?? ""))
  const [resumeLimit, setResumeLimit] = useState(String(initial?.resume_limit ?? ""))
  const [searchLimit, setSearchLimit] = useState(String(initial?.search_limit ?? ""))
  const [stripePriceId, setStripePriceId] = useState(initial?.stripe_price_id ?? "")
  const [trialDays, setTrialDays] = useState(String(initial?.trial_days ?? "0"))
  const [effectiveFrom, setEffectiveFrom] = useState(
    initial?.effective_from ? initial.effective_from.slice(0, 16) : new Date().toISOString().slice(0, 16),
  )
  const [applyToExisting, setApplyToExisting] = useState(initial?.apply_to_existing ?? false)

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave({
          plan,
          billing_cycle: cycle,
          price_usd: parseFloat(price),
          resume_limit: parseInt(resumeLimit),
          search_limit: parseInt(searchLimit),
          stripe_price_id: stripePriceId,
          trial_days: parseInt(trialDays),
          effective_from: new Date(effectiveFrom).toISOString(),
          apply_to_existing: applyToExisting,
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title={title} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Plan">
            <select value={plan} onChange={(e) => setPlan(e.target.value as typeof plan)} className={inputCls}>
              <option value="daily">Daily</option>
              <option value="weekly">Weekly</option>
              <option value="monthly">Monthly</option>
            </select>
          </FormField>

          <FormField label="Billing cycle">
            <select value={cycle} onChange={(e) => setCycle(e.target.value as typeof cycle)} className={inputCls}>
              <option value="recurring">Recurring</option>
              <option value="yearly">Yearly</option>
            </select>
          </FormField>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Price (USD)">
            <input type="number" step="0.01" min="0" required value={price} onChange={(e) => setPrice(e.target.value)} className={inputCls} placeholder="9.99" />
          </FormField>
          <FormField label="Stripe price ID">
            <input type="text" required value={stripePriceId} onChange={(e) => setStripePriceId(e.target.value)} className={inputCls} placeholder="price_..." />
          </FormField>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Resume limit">
            <input type="number" min="1" required value={resumeLimit} onChange={(e) => setResumeLimit(e.target.value)} className={inputCls} />
          </FormField>
          <FormField label="Search limit">
            <input type="number" min="0" required value={searchLimit} onChange={(e) => setSearchLimit(e.target.value)} className={inputCls} />
          </FormField>
        </div>

        <div className="grid grid-cols-2 gap-4">
          <FormField label="Trial days (0 = none)">
            <input type="number" min="0" required value={trialDays} onChange={(e) => setTrialDays(e.target.value)} className={inputCls} />
          </FormField>
          <FormField label="Effective from">
            <input type="datetime-local" required value={effectiveFrom} onChange={(e) => setEffectiveFrom(e.target.value)} className={inputCls} />
          </FormField>
        </div>

        <div>
          <p className="text-sm text-slate-300 mb-2">Apply to:</p>
          <div className="flex gap-4">
            <RadioOpt label="New subscribers only" checked={!applyToExisting} onChange={() => setApplyToExisting(false)} />
            <RadioOpt label="All at next renewal" checked={applyToExisting} onChange={() => setApplyToExisting(true)} />
          </div>
        </div>

        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Save plan" />
      </form>
    </Modal>
  )
}

// ── Add-on pricing modal ──────────────────────────────────────────────────────

function AddonPricingModal({
  initial,
  token: _token,
  onSave,
  onClose,
}: {
  initial: LLMAddonPricing
  token: string
  onSave: (payload: Partial<LLMAddonPricing>) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [values, setValues] = useState({
    better_pack_usd: String(initial.better_pack_usd),
    better_monthly_usd: String(initial.better_monthly_usd),
    better_yearly_usd: String(initial.better_yearly_usd),
    best_per_resume_usd: String(initial.best_per_resume_usd),
    best_monthly_usd: String(initial.best_monthly_usd),
    best_yearly_usd: String(initial.best_yearly_usd),
    free_credit_grant: String(initial.free_credit_grant),
  })

  const fields: Array<{ key: keyof typeof values; label: string }> = [
    { key: "better_pack_usd", label: "Better 5-pack (USD)" },
    { key: "better_monthly_usd", label: "Better monthly (USD)" },
    { key: "better_yearly_usd", label: "Better yearly (USD)" },
    { key: "best_per_resume_usd", label: "Best per-resume (USD)" },
    { key: "best_monthly_usd", label: "Best monthly (USD)" },
    { key: "best_yearly_usd", label: "Best yearly (USD)" },
    { key: "free_credit_grant", label: "Free credit grant" },
  ]

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    startTransition(async () => {
      try {
        const payload: Partial<LLMAddonPricing> = {
          better_pack_usd: parseFloat(values.better_pack_usd),
          better_monthly_usd: parseFloat(values.better_monthly_usd),
          better_yearly_usd: parseFloat(values.better_yearly_usd),
          best_per_resume_usd: parseFloat(values.best_per_resume_usd),
          best_monthly_usd: parseFloat(values.best_monthly_usd),
          best_yearly_usd: parseFloat(values.best_yearly_usd),
          free_credit_grant: parseInt(values.free_credit_grant),
        }
        await onSave(payload)
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title="Edit LLM Add-on Pricing" onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}
        <div className="grid grid-cols-2 gap-4">
          {fields.map(({ key, label }) => (
            <FormField key={key} label={label}>
              <input
                type="number"
                step="0.01"
                min="0"
                required
                value={values[key]}
                onChange={(e) => setValues((v) => ({ ...v, [key]: e.target.value }))}
                className={inputCls}
              />
            </FormField>
          ))}
        </div>
        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Save pricing" />
      </form>
    </Modal>
  )
}

// ── Shared UI atoms ───────────────────────────────────────────────────────────

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

function CycleBadge({ cycle }: { cycle: string }) {
  return (
    <span
      className={clsx(
        "text-xs px-2 py-0.5 rounded-full",
        cycle === "yearly"
          ? "bg-emerald-900/50 text-emerald-300"
          : "bg-slate-700 text-slate-300",
      )}
    >
      {cycle}
    </span>
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

function RadioOpt({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: () => void
}) {
  return (
    <label className="flex items-center gap-2 cursor-pointer text-sm text-slate-300">
      <input
        type="radio"
        checked={checked}
        onChange={onChange}
        className="accent-amber-500"
      />
      {label}
    </label>
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
