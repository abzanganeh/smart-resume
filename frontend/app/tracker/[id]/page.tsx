"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { ArrowLeft, Loader2, Trash2, Upload } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import type { ApplicationStatus } from "@/lib/api"
import {
  addInterviewRound,
  createReminder,
  deleteAttachment,
  formatBytes,
  getApplication,
  listReminders,
  patchApplication,
  upsertOffer,
  uploadAttachment,
  type ApplicationDetail,
  type Reminder,
} from "@/lib/tracker"

const REJECTION_REASONS = [
  { value: "ghosted", label: "Ghosted" },
  { value: "explicit_rejection", label: "Explicit rejection" },
  { value: "position_filled", label: "Position filled" },
  { value: "withdrew", label: "Withdrew" },
  { value: "other", label: "Other" },
]

const INTERVIEW_FORMATS = ["phone", "video", "onsite", "take_home", "other"]

export default function ApplicationDetailPage({
  params,
}: {
  params: Promise<{ id: string }>
}) {
  const { session, status } = useRequireAuth("/tracker")
  const token = session?.backendAccessToken
  const [appId, setAppId] = useState<string | null>(null)
  const [app, setApp] = useState<ApplicationDetail | null>(null)
  const [reminders, setReminders] = useState<Reminder[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)

  const [contactForm, setContactForm] = useState({
    contact_name: "",
    contact_email: "",
    job_url: "",
    notes: "",
  })
  const [roundForm, setRoundForm] = useState({
    name: "",
    format: "video",
    scheduled_at: "",
    duration_minutes: "",
    interviewers: "",
    outcome: "",
  })
  const [offerForm, setOfferForm] = useState({
    base_salary_usd: "",
    bonus_usd: "",
    equity_description: "",
    start_date: "",
    response_deadline: "",
    decision: "pending",
    decision_notes: "",
  })
  const [rejectForm, setRejectForm] = useState({
    status: "rejected" as "rejected" | "withdrawn",
    rejection_reason: "other",
    rejection_notes: "",
  })
  const [reminderForm, setReminderForm] = useState({ scheduled_at: "", message: "" })

  useEffect(() => {
    void params.then((p) => setAppId(p.id))
  }, [params])

  const load = useCallback(async () => {
    if (!token || !appId) return
    setLoading(true)
    setError(null)
    try {
      const [detail, rems] = await Promise.all([
        getApplication(token, appId),
        listReminders(token, appId),
      ])
      setApp(detail)
      setReminders(rems)
      setContactForm({
        contact_name: detail.contact_name ?? "",
        contact_email: detail.contact_email ?? "",
        job_url: detail.job_url ?? "",
        notes: detail.notes ?? "",
      })
      if (detail.offer_detail) {
        setOfferForm({
          base_salary_usd: detail.offer_detail.base_salary_usd?.toString() ?? "",
          bonus_usd: detail.offer_detail.bonus_usd?.toString() ?? "",
          equity_description: detail.offer_detail.equity_description ?? "",
          start_date: detail.offer_detail.start_date ?? "",
          response_deadline: detail.offer_detail.response_deadline?.slice(0, 16) ?? "",
          decision: detail.offer_detail.decision ?? "pending",
          decision_notes: detail.offer_detail.decision_notes ?? "",
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load application")
    } finally {
      setLoading(false)
    }
  }, [token, appId])

  useEffect(() => {
    void load()
  }, [load])

  async function saveContact(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !appId) return
    setSaving(true)
    try {
      await patchApplication(token, appId, contactForm)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Save failed")
    } finally {
      setSaving(false)
    }
  }

  async function submitRound(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !appId) return
    setSaving(true)
    try {
      await addInterviewRound(token, appId, {
        name: roundForm.name,
        format: roundForm.format,
        scheduled_at: roundForm.scheduled_at || undefined,
        duration_minutes: roundForm.duration_minutes
          ? Number(roundForm.duration_minutes)
          : undefined,
        interviewers: roundForm.interviewers
          ? roundForm.interviewers.split(",").map((s) => s.trim()).filter(Boolean)
          : [],
        outcome: roundForm.outcome || undefined,
      })
      setRoundForm({
        name: "",
        format: "video",
        scheduled_at: "",
        duration_minutes: "",
        interviewers: "",
        outcome: "",
      })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to add round")
    } finally {
      setSaving(false)
    }
  }

  async function submitOffer(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !appId || !app) return
    setSaving(true)
    try {
      const body = {
        base_salary_usd: offerForm.base_salary_usd
          ? Number(offerForm.base_salary_usd)
          : null,
        bonus_usd: offerForm.bonus_usd ? Number(offerForm.bonus_usd) : null,
        equity_description: offerForm.equity_description || null,
        start_date: offerForm.start_date || null,
        response_deadline: offerForm.response_deadline
          ? new Date(offerForm.response_deadline).toISOString()
          : null,
        decision: offerForm.decision || null,
        decision_notes: offerForm.decision_notes || null,
      }
      await upsertOffer(token, appId, body, app.offer_detail ? "PATCH" : "POST")
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save offer")
    } finally {
      setSaving(false)
    }
  }

  async function submitRejection(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !appId) return
    setSaving(true)
    try {
      await patchApplication(token, appId, {
        status: rejectForm.status,
        rejection_reason: rejectForm.rejection_reason,
        rejection_notes: rejectForm.rejection_notes || null,
      })
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to update status")
    } finally {
      setSaving(false)
    }
  }

  async function onFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file || !token || !appId) return
    if (file.size > 5 * 1024 * 1024) {
      setError("File exceeds 5 MB limit")
      return
    }
    setSaving(true)
    try {
      await uploadAttachment(token, appId, file)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Upload failed")
    } finally {
      setSaving(false)
      e.target.value = ""
    }
  }

  async function onDeleteAttachment(attachmentId: string) {
    if (!token || !appId) return
    setSaving(true)
    try {
      await deleteAttachment(token, appId, attachmentId)
      await load()
    } catch (err) {
      setError(err instanceof Error ? err.message : "Delete failed")
    } finally {
      setSaving(false)
    }
  }

  async function submitReminder(e: React.FormEvent) {
    e.preventDefault()
    if (!token || !appId) return
    setSaving(true)
    try {
      await createReminder(token, appId, {
        scheduled_at: new Date(reminderForm.scheduled_at).toISOString(),
        message: reminderForm.message,
      })
      setReminderForm({ scheduled_at: "", message: "" })
      const rems = await listReminders(token, appId)
      setReminders(rems)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create reminder")
    } finally {
      setSaving(false)
    }
  }

  if (status === "loading" || !token || loading || !app) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  const usage = app.attachment_usage
  const usagePct = Math.min(
    100,
    (usage.total_bytes / usage.max_total_bytes) * 100,
  )

  return (
    <div className="max-w-4xl mx-auto px-4 py-8">
      <Link
        href="/tracker"
        className="inline-flex items-center gap-1 text-sm text-slate-400 hover:text-amber-300 mb-4"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to pipeline
      </Link>

      <header className="mb-8">
        <p className="text-xs uppercase tracking-wide text-amber-400/80">{app.status}</p>
        <h1 className="text-2xl font-semibold text-white">{app.jd_title}</h1>
        <p className="text-slate-400">{app.jd_company}</p>
      </header>

      {error && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">Timeline</h2>
        <ol className="space-y-4 border-l border-slate-800 ml-2 pl-4">
          {app.timeline.length === 0 && (
            <li className="text-sm text-slate-500">No events yet.</li>
          )}
          {app.timeline.map((ev, i) => (
            <li key={`${ev.type}-${ev.at}-${i}`} className="relative">
              <span className="absolute -left-[21px] top-1.5 w-2.5 h-2.5 rounded-full bg-amber-400/80" />
              <p className="text-xs text-slate-500">{new Date(ev.at).toLocaleString()}</p>
              <p className="text-sm text-slate-200">
                {ev.type === "status_change" && `Status → ${String(ev.status)}`}
                {ev.type === "interview_round" && `Interview: ${String(ev.name)}`}
                {ev.type === "attachment" && `Uploaded ${String(ev.filename)}`}
                {ev.type === "notes" && "Notes updated"}
              </p>
            </li>
          ))}
        </ol>
      </section>

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">Contact &amp; notes</h2>
        <form onSubmit={saveContact} className="grid gap-3 sm:grid-cols-2">
          <input
            placeholder="Contact name"
            value={contactForm.contact_name}
            onChange={(e) =>
              setContactForm((f) => ({ ...f, contact_name: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <input
            placeholder="Contact email"
            type="email"
            value={contactForm.contact_email}
            onChange={(e) =>
              setContactForm((f) => ({ ...f, contact_email: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <input
            placeholder="Job URL"
            value={contactForm.job_url}
            onChange={(e) => setContactForm((f) => ({ ...f, job_url: e.target.value }))}
            className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <textarea
            placeholder="Notes"
            rows={3}
            value={contactForm.notes}
            onChange={(e) => setContactForm((f) => ({ ...f, notes: e.target.value }))}
            className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <button
            type="submit"
            disabled={saving}
            className="sm:col-span-2 w-fit px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold disabled:opacity-50"
          >
            Save contact details
          </button>
        </form>
      </section>

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">Interview rounds</h2>
        {app.interview_rounds.length > 0 && (
          <ul className="mb-4 space-y-2">
            {app.interview_rounds.map((r) => (
              <li
                key={r.id}
                className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
              >
                <span className="text-white font-medium">{r.name}</span>
                <span className="text-slate-500 ml-2">({r.format})</span>
                {r.scheduled_at && (
                  <p className="text-xs text-slate-500 mt-1">
                    {new Date(r.scheduled_at).toLocaleString()}
                  </p>
                )}
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={submitRound} className="grid gap-3 sm:grid-cols-2">
          <input
            required
            placeholder="Round name"
            value={roundForm.name}
            onChange={(e) => setRoundForm((f) => ({ ...f, name: e.target.value }))}
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <select
            value={roundForm.format}
            onChange={(e) => setRoundForm((f) => ({ ...f, format: e.target.value }))}
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          >
            {INTERVIEW_FORMATS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <input
            type="datetime-local"
            value={roundForm.scheduled_at}
            onChange={(e) =>
              setRoundForm((f) => ({ ...f, scheduled_at: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <input
            placeholder="Duration (minutes)"
            value={roundForm.duration_minutes}
            onChange={(e) =>
              setRoundForm((f) => ({ ...f, duration_minutes: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <input
            placeholder="Interviewers (comma-separated)"
            value={roundForm.interviewers}
            onChange={(e) =>
              setRoundForm((f) => ({ ...f, interviewers: e.target.value }))
            }
            className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <button
            type="submit"
            disabled={saving}
            className="sm:col-span-2 w-fit px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold disabled:opacity-50"
          >
            Add interview round
          </button>
        </form>
      </section>

      {(app.status === "offer" || app.offer_detail) && (
        <section className="mb-8 rounded-xl border border-amber-400/30 bg-amber-400/5 p-5">
          <h2 className="text-sm font-semibold text-amber-200 mb-4">Offer details</h2>
          <form onSubmit={submitOffer} className="grid gap-3 sm:grid-cols-2">
            <input
              placeholder="Base salary (USD)"
              value={offerForm.base_salary_usd}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, base_salary_usd: e.target.value }))
              }
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <input
              placeholder="Bonus (USD)"
              value={offerForm.bonus_usd}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, bonus_usd: e.target.value }))
              }
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <input
              placeholder="Equity description"
              value={offerForm.equity_description}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, equity_description: e.target.value }))
              }
              className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <input
              type="date"
              value={offerForm.start_date}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, start_date: e.target.value }))
              }
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <input
              type="datetime-local"
              value={offerForm.response_deadline}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, response_deadline: e.target.value }))
              }
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <select
              value={offerForm.decision}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, decision: e.target.value }))
              }
              className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            >
              <option value="pending">Pending</option>
              <option value="accepted">Accepted</option>
              <option value="declined">Declined</option>
            </select>
            <textarea
              placeholder="Decision notes"
              rows={2}
              value={offerForm.decision_notes}
              onChange={(e) =>
                setOfferForm((f) => ({ ...f, decision_notes: e.target.value }))
              }
              className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
            />
            <button
              type="submit"
              disabled={saving}
              className="sm:col-span-2 w-fit px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold disabled:opacity-50"
            >
              Save offer
            </button>
          </form>
        </section>
      )}

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-2">Attachments</h2>
        <p className="text-xs text-slate-500 mb-3">
          {usage.count}/{usage.max_count} files · {formatBytes(usage.total_bytes)} /{" "}
          {formatBytes(usage.max_total_bytes)}
        </p>
        <div className="h-2 rounded-full bg-slate-800 mb-4 overflow-hidden">
          <div
            className="h-full bg-amber-400 transition-all"
            style={{ width: `${usagePct}%` }}
          />
        </div>
        <label className="inline-flex items-center gap-2 cursor-pointer text-sm text-amber-300 hover:text-amber-200 mb-4">
          <Upload className="w-4 h-4" />
          Upload file (max 5 MB)
          <input type="file" className="hidden" onChange={onFileUpload} disabled={saving} />
        </label>
        <ul className="space-y-2">
          {app.attachments.map((att) => (
            <li
              key={att.id}
              className="flex items-center justify-between rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
            >
              <div>
                <p className="text-slate-200">{att.filename}</p>
                <p className="text-xs text-slate-500">{formatBytes(att.size_bytes)}</p>
              </div>
              <div className="flex items-center gap-2">
                {att.download_url && (
                  <a
                    href={att.download_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-xs text-amber-400 hover:underline"
                  >
                    Download
                  </a>
                )}
                <button
                  type="button"
                  onClick={() => void onDeleteAttachment(att.id)}
                  className="text-slate-500 hover:text-red-400"
                  aria-label="Delete attachment"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            </li>
          ))}
        </ul>
      </section>

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">
          Rejection / withdrawal
        </h2>
        <form onSubmit={submitRejection} className="grid gap-3 sm:grid-cols-2">
          <select
            value={rejectForm.status}
            onChange={(e) =>
              setRejectForm((f) => ({
                ...f,
                status: e.target.value as "rejected" | "withdrawn",
              }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          >
            <option value="rejected">Rejected</option>
            <option value="withdrawn">Withdrawn</option>
          </select>
          <select
            value={rejectForm.rejection_reason}
            onChange={(e) =>
              setRejectForm((f) => ({ ...f, rejection_reason: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          >
            {REJECTION_REASONS.map((r) => (
              <option key={r.value} value={r.value}>
                {r.label}
              </option>
            ))}
          </select>
          <textarea
            placeholder="Optional notes"
            rows={2}
            value={rejectForm.rejection_notes}
            onChange={(e) =>
              setRejectForm((f) => ({ ...f, rejection_notes: e.target.value }))
            }
            className="sm:col-span-2 rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <button
            type="submit"
            disabled={saving}
            className="sm:col-span-2 w-fit px-4 py-2 rounded-lg border border-slate-600 text-slate-300 text-sm hover:bg-slate-800 disabled:opacity-50"
          >
            Update rejection / withdrawal
          </button>
        </form>
      </section>

      <section className="mb-8 rounded-xl border border-slate-800 bg-slate-950/50 p-5">
        <h2 className="text-sm font-semibold text-slate-200 mb-4">Reminders</h2>
        {reminders.length > 0 && (
          <ul className="mb-4 space-y-2">
            {reminders.map((r) => (
              <li
                key={r.id}
                className="rounded-lg border border-slate-800 bg-slate-900 px-3 py-2 text-sm"
              >
                <p className="text-slate-200">{r.message}</p>
                <p className="text-xs text-slate-500">
                  {new Date(r.scheduled_at).toLocaleString()} · {r.status}
                </p>
              </li>
            ))}
          </ul>
        )}
        <form onSubmit={submitReminder} className="grid gap-3">
          <input
            required
            type="datetime-local"
            value={reminderForm.scheduled_at}
            onChange={(e) =>
              setReminderForm((f) => ({ ...f, scheduled_at: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <input
            required
            placeholder="Reminder message"
            value={reminderForm.message}
            onChange={(e) =>
              setReminderForm((f) => ({ ...f, message: e.target.value }))
            }
            className="rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200"
          />
          <button
            type="submit"
            disabled={saving}
            className="w-fit px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold disabled:opacity-50"
          >
            Add reminder
          </button>
        </form>
      </section>
    </div>
  )
}
