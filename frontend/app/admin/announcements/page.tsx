"use client"

import { useEffect, useState, useTransition } from "react"
import { Plus, Trash2, Loader2, X, Bell, AlertTriangle, Wrench } from "lucide-react"
import { clsx } from "clsx"
import { useAdminSession, useAuditToast } from "@/app/admin/layout"
import {
  getAdminAnnouncements,
  createAdminAnnouncement,
  deleteAdminAnnouncement,
} from "@/lib/admin/api"
import type { Announcement, AnnouncementPayload, AnnouncementSeverity } from "@/lib/admin/types"

const SEVERITY_STYLES: Record<
  AnnouncementSeverity,
  { bg: string; text: string; icon: React.ElementType; label: string }
> = {
  info: { bg: "bg-blue-900/40 border-blue-700/50", text: "text-blue-300", icon: Bell, label: "Info" },
  warning: { bg: "bg-amber-900/40 border-amber-700/50", text: "text-amber-300", icon: AlertTriangle, label: "Warning" },
  maintenance: { bg: "bg-slate-800 border-slate-600", text: "text-slate-300", icon: Wrench, label: "Maintenance" },
}

// ── Announcements Page ────────────────────────────────────────────────────────

export default function AdminAnnouncementsPage() {
  const { token } = useAdminSession()
  const { showAuditToast } = useAuditToast()

  const [announcements, setAnnouncements] = useState<Announcement[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showCreate, setShowCreate] = useState(false)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    if (!token) return
    loadAnnouncements()
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  async function loadAnnouncements() {
    setLoading(true)
    setError(null)
    try {
      const res = await getAdminAnnouncements(token!)
      setAnnouncements(Array.isArray(res.announcements) ? res.announcements : [])
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load announcements")
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(id: string) {
    setDeletingId(id)
    try {
      const res = await deleteAdminAnnouncement(token!, id)
      showAuditToast(res.audit_log_id)
      setAnnouncements((prev) => prev.filter((a) => a.id !== id))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Delete failed")
    } finally {
      setDeletingId(null)
    }
  }

  if (!token) return <NotAuthed />
  if (loading) return <PageSpinner />
  if (error) return <PageError msg={error} onRetry={loadAnnouncements} />

  const now = new Date()
  const active = announcements.filter(
    (a) => new Date(a.starts_at) <= now && new Date(a.ends_at) >= now,
  )
  const scheduled = announcements.filter((a) => new Date(a.starts_at) > now)
  const past = announcements.filter((a) => new Date(a.ends_at) < now)

  return (
    <div className="space-y-6 max-w-4xl">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold text-white">Announcements</h1>
        <button
          onClick={() => setShowCreate(true)}
          className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors"
        >
          <Plus className="w-4 h-4" />
          Schedule announcement
        </button>
      </div>

      {/* Active */}
      {active.length > 0 && (
        <AnnouncementGroup
          title="Active Now"
          items={active}
          deletingId={deletingId}
          onDelete={handleDelete}
        />
      )}

      {/* Scheduled */}
      {scheduled.length > 0 && (
        <AnnouncementGroup
          title="Scheduled"
          items={scheduled}
          deletingId={deletingId}
          onDelete={handleDelete}
        />
      )}

      {/* Past */}
      {past.length > 0 && (
        <AnnouncementGroup
          title="Past"
          items={past}
          deletingId={deletingId}
          onDelete={handleDelete}
          muted
        />
      )}

      {announcements.length === 0 && (
        <div className="bg-slate-900 border border-slate-800 rounded-xl px-5 py-12 text-center text-slate-500 text-sm">
          No announcements yet.
        </div>
      )}

      {/* Create modal */}
      {showCreate && (
        <AnnouncementCreateModal
          token={token}
          onSave={async (payload) => {
            const res = await createAdminAnnouncement(token, payload)
            showAuditToast(res.audit_log_id)
            setAnnouncements((prev) => [...prev, res.data])
            setShowCreate(false)
          }}
          onClose={() => setShowCreate(false)}
        />
      )}
    </div>
  )
}

// ── Announcement group ────────────────────────────────────────────────────────

function AnnouncementGroup({
  title,
  items,
  deletingId,
  onDelete,
  muted = false,
}: {
  title: string
  items: Announcement[]
  deletingId: string | null
  onDelete: (id: string) => void
  muted?: boolean
}) {
  return (
    <div className="space-y-3">
      <h2 className={clsx("text-sm font-medium", muted ? "text-slate-500" : "text-slate-300")}>
        {title} ({items.length})
      </h2>
      {items.map((a) => {
        const s = SEVERITY_STYLES[a.severity]
        const Icon = s.icon
        return (
          <div
            key={a.id}
            className={clsx(
              "border rounded-xl p-4 flex gap-4 items-start",
              muted ? "bg-slate-900/50 border-slate-800 opacity-60" : s.bg,
            )}
          >
            <div className={clsx("mt-0.5 shrink-0", s.text)}>
              <Icon className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0 space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <p className={clsx("font-medium text-sm", muted ? "text-slate-300" : s.text)}>
                  {a.title}
                </p>
                <SeverityBadge severity={a.severity} />
              </div>
              {a.body_markdown && (
                <p className="text-xs text-slate-400 line-clamp-2">{a.body_markdown}</p>
              )}
              {a.cta_label && a.cta_url && (
                <p className="text-xs text-slate-400">
                  CTA: <span className="text-amber-400">{a.cta_label}</span> → {a.cta_url}
                </p>
              )}
              <p className="text-xs text-slate-500">
                {new Date(a.starts_at).toLocaleString()} – {new Date(a.ends_at).toLocaleString()}
              </p>
            </div>
            <button
              onClick={() => onDelete(a.id)}
              disabled={deletingId === a.id}
              className="shrink-0 text-slate-500 hover:text-red-400 transition-colors disabled:opacity-40"
              title="Delete"
            >
              {deletingId === a.id ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Trash2 className="w-4 h-4" />
              )}
            </button>
          </div>
        )
      })}
    </div>
  )
}

// ── Create Modal ──────────────────────────────────────────────────────────────

function AnnouncementCreateModal({
  token: _token,
  onSave,
  onClose,
}: {
  token: string
  onSave: (payload: AnnouncementPayload) => Promise<void>
  onClose: () => void
}) {
  const [isPending, startTransition] = useTransition()
  const [err, setErr] = useState<string | null>(null)
  const [title, setTitle] = useState("")
  const [body, setBody] = useState("")
  const [severity, setSeverity] = useState<AnnouncementSeverity>("info")
  const [ctaLabel, setCtaLabel] = useState("")
  const [ctaUrl, setCtaUrl] = useState("")
  const nowLocal = new Date(Date.now() - new Date().getTimezoneOffset() * 60000)
    .toISOString()
    .slice(0, 16)
  const [startsAt, setStartsAt] = useState(nowLocal)
  const [endsAt, setEndsAt] = useState(
    new Date(Date.now() - new Date().getTimezoneOffset() * 60000 + 2 * 3600 * 1000)
      .toISOString()
      .slice(0, 16),
  )

  const inputCls =
    "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-amber-500/50 focus:border-amber-500"

  function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    setErr(null)
    startTransition(async () => {
      try {
        await onSave({
          title,
          body_markdown: body,
          severity,
          cta_label: ctaLabel || undefined,
          cta_url: ctaUrl || undefined,
          starts_at: new Date(startsAt).toISOString(),
          ends_at: new Date(endsAt).toISOString(),
        })
      } catch (e) {
        setErr(e instanceof Error ? e.message : "Create failed")
      }
    })
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
      <div className="bg-slate-900 border border-slate-700 rounded-xl w-full max-w-lg max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h3 className="font-medium text-white">Schedule Announcement</h3>
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
            <label className="block text-xs text-slate-400 mb-1.5">Title</label>
            <input type="text" required value={title} onChange={(e) => setTitle(e.target.value)} className={inputCls} placeholder="Scheduled maintenance on June 1st" />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1.5">Body (Markdown)</label>
            <textarea rows={3} value={body} onChange={(e) => setBody(e.target.value)} className={inputCls + " resize-none"} placeholder="We'll be down for ~30 minutes..." />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-2">Severity</label>
            <div className="flex gap-3">
              {(["info", "warning", "maintenance"] as AnnouncementSeverity[]).map((s) => (
                <label key={s} className="flex items-center gap-2 cursor-pointer text-sm text-slate-300">
                  <input type="radio" checked={severity === s} onChange={() => setSeverity(s)} className="accent-amber-500" />
                  <SeverityBadge severity={s} />
                </label>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">CTA label (optional)</label>
              <input type="text" value={ctaLabel} onChange={(e) => setCtaLabel(e.target.value)} className={inputCls} placeholder="Learn more" />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">CTA URL (optional)</label>
              <input type="url" value={ctaUrl} onChange={(e) => setCtaUrl(e.target.value)} className={inputCls} placeholder="https://status.example.com" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Starts at</label>
              <input type="datetime-local" required value={startsAt} onChange={(e) => setStartsAt(e.target.value)} className={inputCls} />
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1.5">Ends at</label>
              <input type="datetime-local" required value={endsAt} onChange={(e) => setEndsAt(e.target.value)} className={inputCls} />
            </div>
          </div>

          <div className="flex gap-3 justify-end pt-2">
            <button type="button" onClick={onClose} className="px-4 py-2 text-sm text-slate-400 hover:text-white transition-colors">Cancel</button>
            <button type="submit" disabled={isPending} className="flex items-center gap-2 bg-amber-600 hover:bg-amber-500 disabled:opacity-50 text-white text-sm font-medium px-4 py-2 rounded-lg transition-colors">
              {isPending && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
              Schedule
            </button>
          </div>
        </form>
      </div>
    </div>
  )
}

// ── Severity badge ────────────────────────────────────────────────────────────

function SeverityBadge({ severity }: { severity: AnnouncementSeverity }) {
  const s = SEVERITY_STYLES[severity]
  return (
    <span className={clsx("text-xs px-2 py-0.5 rounded-full border", s.bg, s.text)}>
      {s.label}
    </span>
  )
}

// ── Shared ────────────────────────────────────────────────────────────────────

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
