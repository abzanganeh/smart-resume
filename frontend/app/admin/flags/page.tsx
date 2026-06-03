"use client"

import { useEffect, useState, useTransition } from "react"
import { Plus, Loader2, X } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminFeatureFlags,
  createAdminFeatureFlag,
  patchAdminFeatureFlag,
} from "@/lib/admin/api"
import type { FeatureFlag, FeatureFlagPatchPayload } from "@/lib/admin/types"

// ── Feature Flags Page ────────────────────────────────────────────────────────

export default function AdminFlagsPage() {
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [flags, setFlags] = useState<FeatureFlag[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [expandedKey, setExpandedKey] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    loadFlags()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadFlags() {
    setLoading(true)
    setError(null)
    try {
      const res = await getAdminFeatureFlags(token!)
      setFlags(Array.isArray(res.flags) ? res.flags : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load flags")
    } finally {
      setLoading(false)
    }
  }

  async function handleToggle(flag: FeatureFlag) {
    try {
      const res = await patchAdminFeatureFlag(token!, flag.key, { enabled: !flag.enabled })
      showAuditToast(res.audit_log_id)
      setFlags((prev) => prev.map((f) => (f.key === flag.key ? res.data : f)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Update failed")
    }
  }

  async function handlePatch(key: string, payload: FeatureFlagPatchPayload) {
    const res = await patchAdminFeatureFlag(token!, key, payload)
    showAuditToast(res.audit_log_id)
    setFlags((prev) => prev.map((f) => (f.key === key ? res.data : f)))
  }

  if (!token) return <NotAuthed />
  if (loading) return <PageSpinner />
  if (error) return <PageError msg={error} onRetry={loadFlags} />

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Feature Flags</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          New flag
        </button>
      </div>

      {/* Flags table */}
      <div className="bg-slate-900 border border-slate-800 rounded-xl overflow-hidden">
        <div className="px-5 py-3 border-b border-slate-800">
          <h2 className="text-sm font-medium text-slate-200">
            {flags.length} flag{flags.length !== 1 ? "s" : ""}
          </h2>
        </div>
        <div className="divide-y divide-slate-800">
          {flags.length === 0 && (
            <div className="text-center text-slate-500 py-10 text-sm">
              No feature flags yet.
            </div>
          )}
          {flags.map((flag) => (
            <FlagRow
              key={flag.key}
              flag={flag}
              expanded={expandedKey === flag.key}
              onToggleExpand={() =>
                setExpandedKey((prev) => (prev === flag.key ? null : flag.key))
              }
              onToggleEnabled={() => handleToggle(flag)}
              onPatch={(payload) => handlePatch(flag.key, payload)}
            />
          ))}
        </div>
      </div>

      {/* Create modal */}
      {showCreate && (
        <CreateFlagModal
          token={token}
          onSave={async (key, description) => {
            const res = await createAdminFeatureFlag(token, { key, description, enabled: false })
            showAuditToast(res.audit_log_id)
            setFlags((prev) => [...prev, res.data])
            setShowCreate(false)
          }}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  )
}

// ── Flag Row ──────────────────────────────────────────────────────────────────

function FlagRow({
  flag,
  expanded,
  onToggleExpand,
  onToggleEnabled,
  onPatch,
}: {
  flag: FeatureFlag
  expanded: boolean
  onToggleExpand: () => void
  onToggleEnabled: () => void
  onPatch: (payload: FeatureFlagPatchPayload) => Promise<void>
}) {
  const [rollout, setRollout] = useState(flag.rollout_percent)
  const [rolloutDirty, setRolloutDirty] = useState(false)
  const [savingRollout, setSavingRollout] = useState(false)
  const [allowlist, setAllowlist] = useState(flag.allowlist_emails.join("\n"))
  const [blocklist, setBlocklist] = useState(flag.blocklist_emails.join("\n"))
  const [savingLists, setSavingLists] = useState(false)

  async function saveRollout() {
    setSavingRollout(true)
    try {
      await onPatch({ rollout_percent: rollout })
      setRolloutDirty(false)
    } finally {
      setSavingRollout(false)
    }
  }

  async function saveLists() {
    setSavingLists(true)
    try {
      await onPatch({
        allowlist_emails: allowlist.split("\n").map((e) => e.trim()).filter(Boolean),
        blocklist_emails: blocklist.split("\n").map((e) => e.trim()).filter(Boolean),
      })
    } finally {
      setSavingLists(false)
    }
  }

  return (
    <div>
      {/* Main row */}
      <div
        className="flex items-center gap-4 px-5 py-3.5 hover:bg-slate-800/30 transition-colors cursor-pointer"
        onClick={onToggleExpand}
      >
        {/* Toggle */}
        <button
          onClick={(e) => {
            e.stopPropagation()
            onToggleEnabled()
          }}
          className={clsx(
            "relative inline-flex h-5 w-9 items-center rounded-full transition-colors",
            flag.enabled ? "bg-emerald-600" : "bg-slate-600",
          )}
          title={flag.enabled ? "Disable" : "Enable"}
        >
          <span
            className={clsx(
              "absolute h-3.5 w-3.5 rounded-full bg-white shadow transition-transform",
              flag.enabled ? "translate-x-4" : "translate-x-1",
            )}
          />
        </button>

        {/* Info */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-mono text-white truncate">{flag.key}</p>
          <p className="text-xs text-slate-400 truncate">{flag.description}</p>
        </div>

        {/* Rollout */}
        <span className="text-xs text-slate-400 hidden sm:block shrink-0">
          {flag.rollout_percent}% rollout
        </span>

        {/* Updated */}
        <span className="text-xs text-slate-600 hidden md:block shrink-0">
          {new Date(flag.updated_at).toLocaleDateString()}
        </span>

        {/* Expand indicator */}
        <span className="text-slate-600 text-xs">{expanded ? "▲" : "▼"}</span>
      </div>

      {/* Expanded detail */}
      {expanded && (
        <div
          className="px-5 pb-5 bg-slate-800/20 space-y-5"
          onClick={(e) => e.stopPropagation()}
        >
          {/* Rollout slider */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs text-slate-400">Rollout percent</label>
              <span className="text-sm font-mono text-white">{rollout}%</span>
            </div>
            <div className="flex items-center gap-3">
              <input
                type="range"
                min="0"
                max="100"
                step="1"
                value={rollout}
                onChange={(e) => {
                  setRollout(parseInt(e.target.value))
                  setRolloutDirty(true)
                }}
                className="flex-1 accent-amber-500"
              />
              <button
                disabled={!rolloutDirty || savingRollout}
                onClick={saveRollout}
                className="flex items-center gap-1.5 text-xs bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white px-2.5 py-1.5 rounded-lg transition-colors"
              >
                {savingRollout ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
                Save
              </button>
            </div>
          </div>

          {/* Allowlist / blocklist */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">
                Allowlist emails (one per line)
              </label>
              <textarea
                value={allowlist}
                onChange={(e) => setAllowlist(e.target.value)}
                rows={4}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none"
                placeholder="alice@example.com&#10;bob@example.com"
              />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">
                Blocklist emails (one per line)
              </label>
              <textarea
                value={blocklist}
                onChange={(e) => setBlocklist(e.target.value)}
                rows={4}
                className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-white font-mono placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-500/50 resize-none"
                placeholder="spam@example.com"
              />
            </div>
          </div>
          <div className="flex justify-end">
            <button
              onClick={saveLists}
              disabled={savingLists}
              className="flex items-center gap-2 text-xs bg-amber-600 hover:bg-amber-500 disabled:opacity-40 text-white px-3 py-1.5 rounded-lg transition-colors"
            >
              {savingLists ? <Loader2 className="w-3 h-3 animate-spin" /> : null}
              Save lists
            </button>
          </div>
        </div>
      )}
    </div>
  )
}

// ── Create modal ──────────────────────────────────────────────────────────────

function CreateFlagModal({
  token: _token,
  onSave,
  onClose,
}: {
  token: string
  onSave: (key: string, description: string) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [key, setKey] = useState("")
  const [description, setDescription] = useState("")

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave(key.trim().replace(/\s+/g, "_").toLowerCase(), description)
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Create failed")
      }
    })
  }

  const inputCls =
    "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-md">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="font-medium text-white">New Feature Flag</h3>
          <button onClick={onClose} className="text-slate-500 hover:text-white transition-colors">
            <X className="w-4 h-4" />
          </button>
        </div>
        <form onSubmit={handleSubmit} className="p-5 space-y-4">
          {err && (
            <div className="bg-red-900/30 border border-red-700/50 text-red-300 text-sm px-4 py-3 rounded-lg">
              {err}
            </div>
          )}
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Key (snake_case)</label>
            <input
              type="text"
              required
              value={key}
              onChange={(e) => setKey(e.target.value)}
              className={inputCls}
              placeholder="job_search_enabled"
              pattern="[a-z0-9_]+"
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Description</label>
            <input
              type="text"
              required
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={inputCls}
              placeholder="Enables the job search feature for eligible users"
            />
          </div>
          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">
              Cancel
            </button>
            <button
              type="submit"
              disabled={isPending}
              className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
            >
              {isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Create flag
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Shared helpers ────────────────────────────────────────────────────────────

function NotAuthed() {
  return <div className="flex items-center justify-center h-64 text-slate-400 text-sm">Not authenticated.</div>
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
