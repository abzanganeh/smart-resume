"use client"

import Link from "next/link"
import { useCallback, useEffect, useState } from "react"
import { Loader2, Plus, GripVertical } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { listResumes } from "@/lib/dashboard"
import type { ApplicationStatus } from "@/lib/api"
import {
  PIPELINE_COLUMNS,
  createApplication,
  listApplications,
  patchApplication,
  type ApplicationSummary,
} from "@/lib/tracker"

export default function TrackerPage() {
  const { session, status } = useRequireAuth("/tracker")
  const token = session?.backendAccessToken
  const [apps, setApps] = useState<ApplicationSummary[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showForm, setShowForm] = useState(false)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [form, setForm] = useState({
    mode: "manual" as "manual" | "resume",
    resume_record_id: "",
    jd_title: "",
    jd_company: "",
  })
  const [resumes, setResumes] = useState<{ id: string; jd_title: string; jd_company: string }[]>([])

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [applications, resumeList] = await Promise.all([
        listApplications(token),
        listResumes(token, { page_size: 100 }),
      ])
      setApps(applications)
      setResumes(
        resumeList.items.map((r) => ({
          id: r.id,
          jd_title: r.jd_title,
          jd_company: r.jd_company,
        })),
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load applications")
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    if (!token) return
    try {
      const body =
        form.mode === "resume" && form.resume_record_id
          ? { resume_record_id: form.resume_record_id, status: "draft" as ApplicationStatus }
          : {
              jd_title: form.jd_title,
              jd_company: form.jd_company,
              status: "draft" as ApplicationStatus,
            }
      const created = await createApplication(token, body)
      setApps((prev) => [created, ...prev])
      setShowForm(false)
      setForm({ mode: "manual", resume_record_id: "", jd_title: "", jd_company: "" })
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to create application")
    }
  }

  async function moveApplication(appId: string, newStatus: ApplicationStatus) {
    if (!token) return
    const prev = apps
    setApps((items) =>
      items.map((a) => (a.id === appId ? { ...a, status: newStatus } : a)),
    )
    try {
      await patchApplication(token, appId, { status: newStatus })
    } catch (err) {
      setApps(prev)
      setError(err instanceof Error ? err.message : "Failed to update status")
    }
  }

  function onDrop(column: ApplicationStatus) {
    if (!draggingId) return
    void moveApplication(draggingId, column)
    setDraggingId(null)
  }

  if (status === "loading" || !token) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-8">
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-white">Application tracker</h1>
          <p className="text-slate-400 text-sm mt-1">
            Drag cards between columns to update pipeline status.
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowForm(true)}
          className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-4 py-2 rounded-lg hover:bg-amber-300"
        >
          <Plus className="w-4 h-4" />
          Add application
        </button>
      </div>

      {error && (
        <div className="mb-4 rounded-lg border border-red-800 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form
            onSubmit={handleCreate}
            className="w-full max-w-md rounded-xl border border-slate-800 bg-slate-900 p-6 space-y-4"
          >
            <h2 className="text-lg font-semibold text-white">New application</h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, mode: "resume" }))}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  form.mode === "resume"
                    ? "bg-amber-400/20 text-amber-300 border border-amber-400/40"
                    : "bg-slate-800 text-slate-300"
                }`}
              >
                Link resume
              </button>
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, mode: "manual" }))}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  form.mode === "manual"
                    ? "bg-amber-400/20 text-amber-300 border border-amber-400/40"
                    : "bg-slate-800 text-slate-300"
                }`}
              >
                Enter manually
              </button>
            </div>
            {form.mode === "resume" ? (
              <select
                required
                value={form.resume_record_id}
                onChange={(e) => setForm((f) => ({ ...f, resume_record_id: e.target.value }))}
                className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
              >
                <option value="">Select a resume…</option>
                {resumes.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.jd_title} @ {r.jd_company}
                  </option>
                ))}
              </select>
            ) : (
              <>
                <input
                  required
                  placeholder="Job title"
                  value={form.jd_title}
                  onChange={(e) => setForm((f) => ({ ...f, jd_title: e.target.value }))}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
                />
                <input
                  required
                  placeholder="Company"
                  value={form.jd_company}
                  onChange={(e) => setForm((f) => ({ ...f, jd_company: e.target.value }))}
                  className="w-full rounded-lg bg-slate-950 border border-slate-700 px-3 py-2 text-sm text-slate-200"
                />
              </>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-400 hover:text-slate-200"
              >
                Cancel
              </button>
              <button
                type="submit"
                className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold"
              >
                Create
              </button>
            </div>
          </form>
        </div>
      )}

      {loading ? (
        <div className="flex justify-center py-16">
          <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {PIPELINE_COLUMNS.map((col) => {
            const columnApps = apps.filter((a) => a.status === col.key)
            return (
              <section
                key={col.key}
                className="min-w-[220px] flex-1 rounded-xl border border-slate-800 bg-slate-950/50"
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(col.key)}
              >
                <header className="px-3 py-2 border-b border-slate-800 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-slate-300">{col.label}</h2>
                  <span className="text-xs text-slate-500">{columnApps.length}</span>
                </header>
                <div className="p-2 space-y-2 min-h-[120px]">
                  {col.key === "draft" && (
                    <button
                      type="button"
                      onClick={() => setShowForm(true)}
                      className="w-full border border-dashed border-slate-700 rounded-lg py-2 text-xs text-slate-500 hover:border-amber-400/50 hover:text-amber-300"
                    >
                      + Add application
                    </button>
                  )}
                  {columnApps.map((app) => (
                    <article
                      key={app.id}
                      draggable
                      data-testid={`app-card-${app.id}`}
                      data-status={app.status}
                      onDragStart={() => setDraggingId(app.id)}
                      onDragEnd={() => setDraggingId(null)}
                      className="rounded-lg border border-slate-800 bg-slate-900 p-3 cursor-grab active:cursor-grabbing hover:border-slate-600"
                    >
                      <div className="flex items-start gap-2">
                        <GripVertical className="w-4 h-4 text-slate-600 shrink-0 mt-0.5" />
                        <div className="min-w-0 flex-1">
                          <Link
                            href={`/tracker/${app.id}`}
                            className="block text-sm font-medium text-white hover:text-amber-300 truncate"
                          >
                            {app.jd_title}
                          </Link>
                          <p className="text-xs text-slate-500 truncate">{app.jd_company}</p>
                        </div>
                      </div>
                    </article>
                  ))}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
