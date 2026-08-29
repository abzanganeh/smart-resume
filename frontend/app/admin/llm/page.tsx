"use client"

import { useEffect, useState, useTransition } from "react"
import { Pencil, ChevronDown, ChevronUp, Loader2, X } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminLLMConfigs,
  createAdminLLMConfig,
  getAdminLLMHistory,
  getAdminStepLLMConfigs,
  createAdminStepLLMConfig,
  getAdminModelCatalog,
  updateSimilarityThreshold,
} from "@/lib/admin/api"
import type { LLMConfig, LLMConfigPayload, StepLLMConfig, StepLLMConfigPayload } from "@/lib/admin/types"
import {
  ModelPicker,
  DEFAULT_MODEL_PROVIDERS,
  type ModelCatalog,
} from "@/components/admin/ModelPicker"

const TIERS = ["standard", "better", "best"] as const
const PROVIDERS = DEFAULT_MODEL_PROVIDERS

// ── LLM Config Page ───────────────────────────────────────────────────────────

export default function AdminLLMPage() {
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [configs, setConfigs] = useState<LLMConfig[]>([])
  const [threshold, setThreshold] = useState(0.72)
  const [history, setHistory] = useState<LLMConfig[]>([])
  const [stepPins, setStepPins] = useState<StepLLMConfig[]>([])
  const [modelCatalog, setModelCatalog] = useState<ModelCatalog>({})
  const [editingStep, setEditingStep] = useState<StepLLMConfig | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [editingTier, setEditingTier] = useState<LLMConfig | null>(null)
  const [showHistory, setShowHistory] = useState(false)
  const [thresholdDirty, setThresholdDirty] = useState(false)
  const [savingThreshold, setSavingThreshold] = useState(false)

  useEffect(() => {
    if (!token) return
    loadData()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadData() {
    setLoading(true)
    setError(null)
    try {
      const [res, hist, steps, catalog] = await Promise.all([
        getAdminLLMConfigs(token!),
        getAdminLLMHistory(token!),
        getAdminStepLLMConfigs(token!),
        getAdminModelCatalog(token!),
      ])
      setConfigs(Array.isArray(res.configs) ? res.configs : [])
      setThreshold(res.similarity_threshold ?? 0.72)
      setHistory(Array.isArray(hist) ? hist : [])
      setStepPins(Array.isArray(steps) ? steps : [])
      setModelCatalog(catalog ?? {})
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load LLM configs")
    } finally {
      setLoading(false)
    }
  }

  async function handleSaveThreshold() {
    setSavingThreshold(true)
    try {
      const res = await updateSimilarityThreshold(token!, threshold)
      showAuditToast(res.audit_log_id)
      setThresholdDirty(false)
    } finally {
      setSavingThreshold(false)
    }
  }

  if (!token) return <NotAuthed />
  if (loading) return <PageSpinner />
  if (error) return <PageError msg={error} onRetry={loadData} />

  const byTier = (tier: string) => configs.find((c) => c.tier === tier && c.active)

  return (
    <div className="space-y-8 max-w-5xl">
      <PageHeader title="LLM Configuration" />

      {/* ── Tier cards (legacy metadata) ─────────────────────────────── */}
      <div className="bg-amber-900/20 border border-amber-700/40 text-amber-200 text-sm px-4 py-3 rounded-xl">
        <strong>Tier cards are legacy metadata.</strong> Live self-serve routing uses{" "}
        <strong>Pipeline Step Pins</strong> below (<code className="text-amber-100">resolve_model(step)</code>).
        Editing a tier card does not retarget cover letter, checkup, or other steps.
      </div>

      <Section title="Active Configuration by Tier">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          {TIERS.map((tier) => {
            const cfg = byTier(tier)
            return (
              <div
                key={tier}
                className="bg-slate-800/50 border border-slate-700 rounded-xl p-4 space-y-3"
              >
                <div className="flex items-center justify-between">
                  <TierBadge tier={tier} />
                  <button
                    onClick={() => setEditingTier(cfg ?? ({ tier } as LLMConfig))}
                    className="text-slate-500 hover:text-white transition-colors"
                    title="Edit"
                  >
                    <Pencil className="w-3.5 h-3.5" />
                  </button>
                </div>

                {cfg ? (
                  <div className="space-y-2 text-sm">
                    <Row label="Provider" value={cfg.provider} />
                    <Row label="Model" value={<code className="text-xs text-amber-300">{cfg.model_string}</code>} />
                    <Row
                      label="Phases"
                      value={
                        <span className="text-xs text-slate-400">
                          {cfg.phases_enabled.join(", ")}
                        </span>
                      }
                    />
                    <p className="text-[11px] text-slate-500 pt-1">Legacy — not used for routing</p>
                  </div>
                ) : (
                  <p className="text-sm text-slate-500 italic">Not configured</p>
                )}
              </div>
            )
          })}
        </div>
      </Section>

      {/* ── Pipeline step pins ───────────────────────────────────────── */}
      <Section title="Pipeline Step Pins">
        <p className="text-xs text-slate-500 mb-4">
          Controls which provider/model runs for each pipeline step. Changes take effect immediately — no deploy required.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-800">
                <Th>Step</Th>
                <Th>Provider</Th>
                <Th>Model</Th>
                <Th>Source</Th>
                <Th aria-label="Actions"> </Th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800">
              {stepPins.map((pin) => (
                <tr key={pin.step} className="text-slate-300">
                  <Td>
                    <div className="font-medium text-slate-200">{pin.label}</div>
                    <code className="text-xs text-slate-500">{pin.step}</code>
                  </Td>
                  <Td>{pin.provider}</Td>
                  <Td><code className="text-xs text-amber-300">{pin.model_string}</code></Td>
                  <Td>
                    <span className={clsx(
                      "text-xs px-2 py-0.5 rounded-full",
                      pin.source === "pin" ? "bg-emerald-900/40 text-emerald-300" : "bg-slate-800 text-slate-500",
                    )}>
                      {pin.source}
                    </span>
                  </Td>
                  <Td className="text-right">
                    <button
                      onClick={() => setEditingStep(pin)}
                      className="text-slate-500 hover:text-white transition-colors"
                      title="Edit pin"
                    >
                      <Pencil className="w-3.5 h-3.5" />
                    </button>
                  </Td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      {/* ── Similarity threshold ──────────────────────────────────────── */}
      <Section title="Vector Similarity Threshold">
        <div className="flex items-center gap-6">
          <div className="flex-1">
            <input
              type="range"
              min="0.5"
              max="1.0"
              step="0.01"
              value={threshold}
              onChange={(e) => {
                setThreshold(parseFloat(e.target.value))
                setThresholdDirty(true)
              }}
              className="w-full accent-amber-500"
            />
            <div className="flex justify-between text-xs text-slate-500 mt-1">
              <span>0.5 (broader)</span>
              <span>1.0 (exact)</span>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <span className="text-2xl font-mono font-semibold text-white w-16 text-center">
              {threshold.toFixed(2)}
            </span>
            <button
              disabled={!thresholdDirty || savingThreshold}
              onClick={handleSaveThreshold}
              className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white text-sm px-3 py-1.5 rounded-lg transition-colors"
            >
              {savingThreshold ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
              Save
            </button>
          </div>
        </div>
        <p className="text-xs text-slate-500 mt-3">
          Controls minimum cosine similarity for Master Resume chunk selection. Default: 0.72.
        </p>
      </Section>

      {/* ── Change history ────────────────────────────────────────────── */}
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
                  <Th>Tier</Th>
                  <Th>Provider</Th>
                  <Th>Model</Th>
                  <Th>Cost/resume</Th>
                  <Th>Created</Th>
                  <Th>Status</Th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800">
                {history.map((h) => (
                  <tr key={h.id} className="text-slate-400">
                    <Td><TierBadge tier={h.tier} /></Td>
                    <Td>{h.provider}</Td>
                    <Td><code className="text-xs">{h.model_string}</code></Td>
                    <Td>${h.cost_per_resume_usd.toFixed(4)}</Td>
                    <Td className="text-xs">{new Date(h.created_at).toLocaleString()}</Td>
                    <Td>
                      {h.active ? (
                        <span className="text-emerald-400 text-xs">Active</span>
                      ) : (
                        <span className="text-slate-600 text-xs">Replaced</span>
                      )}
                    </Td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      {/* ── Edit tier modal ───────────────────────────────────────────── */}
      {editingTier !== null && (
        <LLMEditModal
          initial={editingTier}
          catalog={modelCatalog}
          token={token}
          onSave={async (payload) => {
            const res = await createAdminLLMConfig(token, payload)
            showAuditToast(res.audit_log_id)
            setEditingTier(null)
            await loadData()
          }}
          onClose={() => setEditingTier(null)}
        />
      )}

      {editingStep !== null && (
        <StepPinEditModal
          initial={editingStep}
          catalog={modelCatalog}
          onSave={async (payload) => {
            const res = await createAdminStepLLMConfig(token, payload)
            showAuditToast(res.audit_log_id)
            setEditingStep(null)
            await loadData()
          }}
          onClose={() => setEditingStep(null)}
        />
      )}
    </div>
  )
}

// ── LLM Edit Modal ────────────────────────────────────────────────────────────

function LLMEditModal({
  initial,
  catalog,
  token: _token,
  onSave,
  onClose,
}: {
  initial: LLMConfig
  catalog: ModelCatalog
  token: string
  onSave: (payload: LLMConfigPayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)

  const [provider, setProvider] = useState(initial.provider ?? "openai")
  const [model, setModel] = useState(initial.model_string ?? "")
  const phases = ["1", "2", "3", "4", "fit", "cover_letter"]
  const [enabledPhases, setEnabledPhases] = useState<string[]>(
    initial.phases_enabled ?? phases,
  )

  function togglePhase(p: string) {
    setEnabledPhases((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p],
    )
  }

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave({
          tier: initial.tier,
          provider,
          model_string: model,
          phases_enabled: enabledPhases,
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title={`Edit ${initial.tier} tier LLM`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}

        <div className="flex items-center gap-2 mb-1">
          <TierBadge tier={initial.tier} />
        </div>

        <p className="text-xs text-slate-500">
          Tier metadata only — pipeline routing uses step pins below.
        </p>

        <ModelPicker
          catalog={catalog}
          provider={provider}
          model={model}
          onProviderChange={setProvider}
          onModelChange={setModel}
          providers={PROVIDERS}
        />

        <div>
          <p className="text-xs text-slate-400 mb-2">Enabled phases</p>
          <div className="flex flex-wrap gap-2">
            {phases.map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => togglePhase(p)}
                className={clsx(
                  "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
                  enabledPhases.includes(p)
                    ? "bg-amber-600/80 text-white"
                    : "bg-slate-700 text-slate-400 hover:bg-slate-600",
                )}
              >
                {p}
              </button>
            ))}
          </div>
        </div>

        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Save config" />
      </form>
    </Modal>
  )
}

// ── Step pin edit modal ───────────────────────────────────────────────────────

function StepPinEditModal({
  initial,
  catalog,
  onSave,
  onClose,
}: {
  initial: StepLLMConfig
  catalog: ModelCatalog
  onSave: (payload: StepLLMConfigPayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [provider, setProvider] = useState(initial.provider)
  const [model, setModel] = useState(initial.model_string)
  const [notes, setNotes] = useState(initial.notes ?? "")

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave({
          step: initial.step,
          provider,
          model_string: model,
          notes: notes || undefined,
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Save failed")
      }
    })
  }

  return (
    <Modal title={`Edit step: ${initial.label}`} onClose={onClose}>
      <form onSubmit={handleSubmit} className="space-y-4">
        {err && <ErrorBanner msg={err} />}
        <p className="text-xs text-slate-500">
          Step id: <code className="text-slate-400">{initial.step}</code>
        </p>
        <ModelPicker
          catalog={catalog}
          provider={provider}
          model={model}
          onProviderChange={setProvider}
          onModelChange={setModel}
          providers={PROVIDERS}
        />
        <FormField label="Notes (optional)">
          <input
            type="text"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            className={inputCls}
            placeholder="Why this pin changed"
          />
        </FormField>
        {!initial.has_price_row && (
          <p className="text-xs text-amber-400">
            Current model has no pricing row — accounting may show $0 until pricing is added.
          </p>
        )}
        <ModalActions onClose={onClose} isPending={isPending} submitLabel="Save pin" />
      </form>
    </Modal>
  )
}

// ── Shared atoms ──────────────────────────────────────────────────────────────

const inputCls =
  "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    standard: "bg-slate-700 text-slate-200",
    better: "bg-amber-900/60 text-amber-300",
    best: "bg-violet-900/60 text-violet-300",
  }
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full font-medium capitalize", colors[tier] ?? colors.standard)}>
      {tier}
    </span>
  )
}

function Row({ label, value }: { label: string; value: React.ReactNode }) {
  return (
    <div className="flex justify-between items-center gap-2">
      <span className="text-slate-400 text-xs shrink-0">{label}</span>
      <span className="text-slate-200 text-right">{value}</span>
    </div>
  )
}

function PageHeader({ title }: { title: string }) {
  return <h1 className="text-xl font-semibold text-white">{title}</h1>
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

function Modal({ title, children, onClose }: { title: string; children: React.ReactNode; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="font-medium text-white">{title}</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors"><X className="w-4 h-4" /></button>
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

function ModalActions({ onClose, isPending, submitLabel }: { onClose: () => void; isPending: boolean; submitLabel: string }) {
  return (
    <div className="flex gap-3 pt-2 justify-end">
      <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
      <button type="submit" disabled={isPending} className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
        {isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
        {submitLabel}
      </button>
    </div>
  )
}

function ErrorBanner({ msg }: { msg: string }) {
  return <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">{msg}</div>
}

function PageSpinner() {
  return <div className="flex items-center justify-center h-64"><Loader2 className="w-8 h-8 animate-spin text-amber-400" /></div>
}

function PageError({ msg, onRetry }: { msg: string; onRetry: () => void }) {
  return (
    <div className="flex flex-col items-center gap-4 h-64 justify-center">
      <p className="text-red-400">{msg}</p>
      <button onClick={onRetry} className="text-sm text-amber-400 hover:underline">Retry</button>
    </div>
  )
}

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
}
