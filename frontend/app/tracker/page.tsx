"use client"

import Link from "next/link"
import { useCallback, useEffect, useRef, useState } from "react"
import {
  Archive,
  ArchiveRestore,
  Crown,
  GripVertical,
  Loader2,
  Plus,
} from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { listResumes } from "@/lib/dashboard"
import type { ApplicationStatus } from "@/lib/api"
import {
  archiveApplication,
  createApplication,
  getApplicationFunnel,
  listApplications,
  patchApplication,
  PIPELINE_COLUMNS,
  TrackerApiError,
  unarchiveApplication,
  type ApplicationFunnelResponse,
  type ApplicationSummary,
} from "@/lib/tracker"

interface CreateForm {
  mode: "manual" | "resume"
  resume_record_id: string
  jd_title: string
  jd_company: string
}

interface DuplicateWarning {
  form: CreateForm
  existingId: string
  message: string
}

const emptyForm: CreateForm = {
  mode: "manual",
  resume_record_id: "",
  jd_title: "",
  jd_company: "",
}

export default function TrackerPage() {
  const { session, status } = useRequireAuth("/tracker")
  const token = session?.backendAccessToken
  const [apps, setApps] = useState<ApplicationSummary[]>([])
  const [funnel, setFunnel] = useState<ApplicationFunnelResponse | null>(null)
  const [showArchived, setShowArchived] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [limitReached, setLimitReached] = useState<{
    message: string
    limit: number
  } | null>(null)
  const [duplicateWarning, setDuplicateWarning] =
    useState<DuplicateWarning | null>(null)
  const [confirmingDuplicate, setConfirmingDuplicate] = useState(false)
  const [showForm, setShowForm] = useState(false)
  const [draggingId, setDraggingId] = useState<string | null>(null)
  const [pendingMoves, setPendingMoves] = useState<
    Record<string, ApplicationStatus>
  >({})
  const pendingStatusRef = useRef<Record<string, ApplicationStatus>>({})
  const debounceRef = useRef<Record<string, ReturnType<typeof setTimeout>>>({})
  const [form, setForm] = useState<CreateForm>(emptyForm)
  const [resumes, setResumes] = useState<
    { id: string; jd_title: string; jd_company: string }[]
  >([])

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [applications, resumeList, funnelData] = await Promise.all([
        listApplications(token, { archived: showArchived ? "all" : "false" }),
        listResumes(token, { page_size: 100 }),
        getApplicationFunnel(token),
      ])
      setApps(applications)
      setResumes(
        resumeList.items.map((r) => ({
          id: r.id,
          jd_title: r.jd_title,
          jd_company: r.jd_company,
        })),
      )
      setFunnel(funnelData)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load applications")
    } finally {
      setLoading(false)
    }
  }, [token, showArchived])

  useEffect(() => {
    void load()
  }, [load])

  useEffect(() => {
    return () => {
      Object.values(debounceRef.current).forEach((timer) => clearTimeout(timer))
    }
  }, [])

  async function submitCreate(payload: {
    body: Parameters<typeof createApplication>[1]
    origin: CreateForm
  }): Promise<void> {
    if (!token) return
    try {
      const created = await createApplication(token, payload.body)
      setApps((prev) => [created, ...prev])
      setShowForm(false)
      setDuplicateWarning(null)
      setLimitReached(null)
      setForm(emptyForm)
      // Refresh the funnel so the header stays in sync.
      void getApplicationFunnel(token)
        .then(setFunnel)
        .catch(() => undefined)
    } catch (err) {
      if (err instanceof TrackerApiError) {
        if (err.code === "tracker_limit_reached") {
          const limit = (err.detail?.limit as number | undefined) ?? 0
          setLimitReached({ message: err.message, limit })
          setShowForm(false)
          setDuplicateWarning(null)
          return
        }
        if (err.code === "duplicate_application") {
          setDuplicateWarning({
            form: payload.origin,
            existingId:
              (err.detail?.existing_id as string | undefined) ?? "",
            message: err.message,
          })
          setShowForm(false)
          return
        }
      }
      setError(err instanceof Error ? err.message : "Failed to create application")
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    const body =
      form.mode === "resume" && form.resume_record_id
        ? {
            resume_record_id: form.resume_record_id,
            status: "draft" as ApplicationStatus,
          }
        : {
            jd_title: form.jd_title,
            jd_company: form.jd_company,
            status: "draft" as ApplicationStatus,
          }
    await submitCreate({ body, origin: form })
  }

  async function confirmDuplicate() {
    // In-flight guard: rapid double-click on "Add anyway" must not
    // submit multiple duplicate creates while the first request is
    // still pending.
    if (!duplicateWarning || confirmingDuplicate) return
    const origin = duplicateWarning.form
    const body =
      origin.mode === "resume" && origin.resume_record_id
        ? {
            resume_record_id: origin.resume_record_id,
            status: "draft" as ApplicationStatus,
            confirm_add_duplicate: true,
          }
        : {
            jd_title: origin.jd_title,
            jd_company: origin.jd_company,
            status: "draft" as ApplicationStatus,
            confirm_add_duplicate: true,
          }
    setConfirmingDuplicate(true)
    try {
      await submitCreate({ body, origin })
    } finally {
      setConfirmingDuplicate(false)
    }
  }

  async function moveApplication(
    appId: string,
    newStatus: ApplicationStatus,
  ) {
    if (!token) return
    const currentStatus = apps.find((a) => a.id === appId)?.status
    if (!currentStatus || currentStatus === newStatus) return
    const prev = apps
    setApps((items) =>
      items.map((a) => (a.id === appId ? { ...a, status: newStatus } : a)),
    )
    pendingStatusRef.current[appId] = newStatus
    setPendingMoves((curr) => ({ ...curr, [appId]: newStatus }))
    if (debounceRef.current[appId]) {
      clearTimeout(debounceRef.current[appId])
    }
    debounceRef.current[appId] = setTimeout(async () => {
      try {
        await patchApplication(token, appId, {
          status: pendingStatusRef.current[appId],
        })
      } catch (err) {
        setApps(prev)
        setError(err instanceof Error ? err.message : "Failed to update status")
      } finally {
        delete pendingStatusRef.current[appId]
        setPendingMoves((curr) => {
          const next = { ...curr }
          delete next[appId]
          return next
        })
      }
    }, 250)
  }

  async function handleArchive(appId: string) {
    if (!token) return
    try {
      const updated = await archiveApplication(token, appId)
      setApps((items) =>
        showArchived
          ? items.map((a) => (a.id === appId ? updated : a))
          : items.filter((a) => a.id !== appId),
      )
      void getApplicationFunnel(token)
        .then(setFunnel)
        .catch(() => undefined)
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to archive")
    }
  }

  async function handleUnarchive(appId: string) {
    if (!token) return
    try {
      const updated = await unarchiveApplication(token, appId)
      setApps((items) => items.map((a) => (a.id === appId ? updated : a)))
      void getApplicationFunnel(token)
        .then(setFunnel)
        .catch(() => undefined)
    } catch (err) {
      if (err instanceof TrackerApiError && err.code === "tracker_limit_reached") {
        const limit = (err.detail?.limit as number | undefined) ?? 0
        setLimitReached({ message: err.message, limit })
        return
      }
      setError(err instanceof Error ? err.message : "Failed to unarchive")
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
        <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
      </div>
    )
  }

  const activeLimit = funnel?.tracker_active_limit ?? null
  const activeCount = funnel?.active_total ?? 0

  return (
    <div className="max-w-[1400px] mx-auto px-4 py-8">
      <div className="flex flex-wrap items-start justify-between gap-3 mb-6">
        <div>
          <h1 className="text-2xl font-semibold text-slate-900 dark:text-white">
            Application tracker
          </h1>
          <p className="text-slate-600 dark:text-slate-400 text-sm mt-1">
            Drag cards between columns to update pipeline status.
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
            <input
              type="checkbox"
              checked={showArchived}
              onChange={(e) => setShowArchived(e.target.checked)}
              data-testid="tracker-show-archived"
            />
            Show archived
          </label>
          <button
            type="button"
            onClick={() => {
              setLimitReached(null)
              setShowForm(true)
            }}
            className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-4 py-2 rounded-lg hover:bg-amber-300"
          >
            <Plus className="w-4 h-4" />
            Add application
          </button>
        </div>
      </div>

      {funnel && (
        <section
          className="mb-4 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950/60 px-4 py-3 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-slate-600 dark:text-slate-400"
          aria-label="Application funnel summary"
          data-testid="tracker-funnel-summary"
        >
          <span className="font-semibold text-slate-700 dark:text-slate-300">
            Active {activeCount}
            {activeLimit !== null ? ` / ${activeLimit}` : ""}
          </span>
          {PIPELINE_COLUMNS.map((c) => (
            <span key={c.key} className="tabular-nums">
              {c.label}:{" "}
              <span className="text-slate-700 dark:text-slate-300 font-medium">
                {funnel.status_counts[c.key] ?? 0}
              </span>
            </span>
          ))}
          {funnel.archived_total > 0 && (
            <span className="tabular-nums">
              Archived:{" "}
              <span className="text-slate-700 dark:text-slate-300 font-medium">
                {funnel.archived_total}
              </span>
            </span>
          )}
        </section>
      )}

      {limitReached && (
        <div
          className="mb-4 rounded-lg border border-amber-400/40 bg-amber-50/70 dark:bg-amber-950/40 px-4 py-3 text-sm text-amber-900 dark:text-amber-200 flex flex-wrap items-center justify-between gap-3"
          data-testid="tracker-limit-banner"
        >
          <p className="flex items-center gap-2">
            <Crown className="w-4 h-4" />
            {limitReached.message}
          </p>
          <div className="flex items-center gap-2">
            <Link
              href="/billing"
              className="px-3 py-1.5 bg-amber-400 hover:bg-amber-300 text-slate-900 rounded-lg text-xs font-semibold"
            >
              Upgrade plan
            </Link>
            <button
              type="button"
              onClick={() => setLimitReached(null)}
              className="text-xs text-amber-900/70 dark:text-amber-200/70 hover:text-amber-900 dark:hover:text-amber-100"
            >
              Dismiss
            </button>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 rounded-lg border border-red-200 dark:border-red-800 bg-red-50 dark:bg-red-950/40 px-4 py-3 text-sm text-red-700 dark:text-red-300">
          {error}
        </div>
      )}

      {duplicateWarning && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
          data-testid="tracker-duplicate-modal"
        >
          <div className="w-full max-w-md rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4">
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              Add this application anyway?
            </h2>
            <p className="text-sm text-slate-600 dark:text-slate-300">
              {duplicateWarning.message}
            </p>
            {duplicateWarning.existingId && (
              <Link
                href={`/tracker/${duplicateWarning.existingId}`}
                className="inline-block text-sm text-amber-700 dark:text-amber-300 hover:underline"
                onClick={() => setDuplicateWarning(null)}
              >
                Open the existing one instead →
              </Link>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDuplicateWarning(null)}
                disabled={confirmingDuplicate}
                className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => void confirmDuplicate()}
                disabled={confirmingDuplicate}
                aria-busy={confirmingDuplicate}
                className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold disabled:opacity-60 disabled:cursor-not-allowed"
              >
                {confirmingDuplicate ? "Adding…" : "Add anyway"}
              </button>
            </div>
          </div>
        </div>
      )}

      {showForm && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4">
          <form
            onSubmit={handleCreate}
            className="w-full max-w-md rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6 space-y-4"
          >
            <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
              New application
            </h2>
            <div className="flex gap-2">
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, mode: "resume" }))}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  form.mode === "resume"
                    ? "bg-amber-500/20 dark:bg-amber-400/20 text-amber-700 dark:text-amber-300 border border-amber-400/40"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                }`}
              >
                Link resume
              </button>
              <button
                type="button"
                onClick={() => setForm((f) => ({ ...f, mode: "manual" }))}
                className={`flex-1 py-2 rounded-lg text-sm ${
                  form.mode === "manual"
                    ? "bg-amber-500/20 dark:bg-amber-400/20 text-amber-700 dark:text-amber-300 border border-amber-400/40"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                }`}
              >
                Enter manually
              </button>
            </div>
            {form.mode === "resume" ? (
              <select
                required
                value={form.resume_record_id}
                onChange={(e) =>
                  setForm((f) => ({ ...f, resume_record_id: e.target.value }))
                }
                className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-slate-200"
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
                  onChange={(e) =>
                    setForm((f) => ({ ...f, jd_title: e.target.value }))
                  }
                  className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-slate-200"
                />
                <input
                  required
                  placeholder="Company"
                  value={form.jd_company}
                  onChange={(e) =>
                    setForm((f) => ({ ...f, jd_company: e.target.value }))
                  }
                  className="w-full rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-300 dark:border-slate-700 px-3 py-2 text-sm text-slate-800 dark:text-slate-200"
                />
              </>
            )}
            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setShowForm(false)}
                className="px-4 py-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
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
          <Loader2 className="w-8 h-8 animate-spin text-amber-700 dark:text-amber-400" />
        </div>
      ) : (
        <div className="flex gap-3 overflow-x-auto pb-4">
          {PIPELINE_COLUMNS.map((col) => {
            const columnApps = apps.filter((a) => a.status === col.key)
            return (
              <section
                key={col.key}
                className="min-w-[220px] flex-1 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/50"
                onDragOver={(e) => e.preventDefault()}
                onDrop={() => onDrop(col.key)}
              >
                <header className="px-3 py-2 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <h2 className="text-sm font-medium text-slate-700 dark:text-slate-300">
                    {col.label}
                  </h2>
                  <span className="text-xs text-slate-600 dark:text-slate-400">
                    {columnApps.length}
                  </span>
                </header>
                <div className="p-2 space-y-2 min-h-[120px]">
                  {col.key === "draft" && (
                    <button
                      type="button"
                      onClick={() => {
                        setLimitReached(null)
                        setShowForm(true)
                      }}
                      className="w-full border border-dashed border-slate-300 dark:border-slate-700 rounded-lg py-2 text-xs text-slate-600 dark:text-slate-400 hover:border-amber-400/50 hover:text-amber-800 dark:hover:text-amber-300"
                    >
                      + Add application
                    </button>
                  )}
                  {columnApps.map((app) => {
                    const isArchived = app.archived_at !== null
                    return (
                      <article
                        key={app.id}
                        draggable={!isArchived}
                        data-testid={`app-card-${app.id}`}
                        data-status={app.status}
                        data-archived={isArchived ? "true" : "false"}
                        onDragStart={() => setDraggingId(app.id)}
                        onDragEnd={() => setDraggingId(null)}
                        className={`rounded-lg border p-3 hover:border-slate-600 ${
                          isArchived
                            ? "border-dashed border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/60 opacity-70"
                            : "border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 cursor-grab active:cursor-grabbing"
                        }`}
                      >
                        <div className="flex items-start gap-2">
                          {!isArchived && (
                            <GripVertical className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0 mt-0.5" />
                          )}
                          <div className="min-w-0 flex-1">
                            <Link
                              href={`/tracker/${app.id}`}
                              className="block text-sm font-medium text-slate-900 dark:text-white hover:text-amber-800 dark:hover:text-amber-300 truncate"
                            >
                              {app.jd_title}
                            </Link>
                            <p className="text-xs text-slate-600 dark:text-slate-400 truncate">
                              {app.jd_company}
                            </p>
                            {pendingMoves[app.id] && (
                              <p className="text-[11px] text-amber-700 dark:text-amber-400 mt-1">
                                Saving status...
                              </p>
                            )}
                          </div>
                          {isArchived ? (
                            <button
                              type="button"
                              onClick={() => void handleUnarchive(app.id)}
                              className="p-1 text-slate-500 hover:text-emerald-700 dark:hover:text-emerald-400"
                              aria-label="Unarchive"
                              title="Unarchive"
                            >
                              <ArchiveRestore className="w-4 h-4" />
                            </button>
                          ) : (
                            <button
                              type="button"
                              onClick={() => void handleArchive(app.id)}
                              className="p-1 text-slate-500 hover:text-amber-700 dark:hover:text-amber-400"
                              aria-label="Archive"
                              title="Archive"
                            >
                              <Archive className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </article>
                    )
                  })}
                </div>
              </section>
            )
          })}
        </div>
      )}
    </div>
  )
}
