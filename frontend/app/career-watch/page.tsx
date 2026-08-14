"use client"

import Link from "next/link"
import { FormEvent, useCallback, useEffect, useState } from "react"
import { Loader2, Plus, Trash2, ExternalLink } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import {
  createCareerWatch,
  deleteCareerWatch,
  detectCareersPage,
  dismissCareerAlert,
  getCareerWatchLimits,
  listCareerAlerts,
  listCareerWatches,
  type CareerWatchAlert,
  type CareerWatchEntry,
  type CareerWatchLimits,
} from "@/lib/careerWatch"

export default function CareerWatchPage() {
  const { session, status } = useRequireAuth("/career-watch")
  const token = session?.backendAccessToken
  const [watches, setWatches] = useState<CareerWatchEntry[]>([])
  const [alerts, setAlerts] = useState<CareerWatchAlert[]>([])
  const [limits, setLimits] = useState<CareerWatchLimits | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [url, setUrl] = useState("")
  const [keywords, setKeywords] = useState("")
  const [companyName, setCompanyName] = useState("")
  const [detectedAts, setDetectedAts] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  const load = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [watchRows, alertRows, limitRows] = await Promise.all([
        listCareerWatches(token),
        listCareerAlerts(token),
        getCareerWatchLimits(token),
      ])
      setWatches(watchRows)
      setAlerts(alertRows)
      setLimits(limitRows)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load Career Watch")
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    void load()
  }, [load])

  async function handleDetect() {
    if (!token || !url.trim()) return
    try {
      const result = await detectCareersPage(token, url.trim())
      setDetectedAts(result.ats_type)
      if (result.company_name && !companyName) {
        setCompanyName(result.company_name)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Detection failed")
    }
  }

  async function handleAdd(e: FormEvent) {
    e.preventDefault()
    if (!token || !url.trim()) return
    setSubmitting(true)
    setError(null)
    try {
      const kw = keywords
        .split(",")
        .map((k) => k.trim())
        .filter(Boolean)
      await createCareerWatch(token, {
        careers_page_url: url.trim(),
        company_name: companyName.trim() || undefined,
        keywords: kw,
      })
      setUrl("")
      setKeywords("")
      setCompanyName("")
      setDetectedAts(null)
      await load()
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to add company")
    } finally {
      setSubmitting(false)
    }
  }

  async function handleRemove(watchId: string) {
    if (!token) return
    await deleteCareerWatch(token, watchId)
    await load()
  }

  async function handleDismiss(alertId: string) {
    if (!token) return
    await dismissCareerAlert(token, alertId)
    await load()
  }

  if (status === "loading" || loading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
      </div>
    )
  }

  return (
    <div className="mx-auto max-w-4xl space-y-8 p-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Career Watch</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Monitor company career pages and get alerted when matching roles appear.
        </p>
        {limits && (
          <p className="mt-2 text-xs text-muted-foreground">
            {limits.active_watches} / {limits.max_companies} companies watched · polls
            every {limits.poll_interval_minutes} min
          </p>
        )}
      </div>

      {error && (
        <div className="rounded-md border border-destructive/40 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <form onSubmit={handleAdd} className="space-y-4 rounded-lg border p-4">
        <h2 className="font-medium">Add company</h2>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="cw-url">
            Careers page URL
          </label>
          <div className="flex gap-2">
            <input
              id="cw-url"
              className="flex-1 rounded-md border px-3 py-2 text-sm"
              placeholder="https://boards.greenhouse.io/acme"
              value={url}
              onChange={(e) => setUrl(e.target.value)}
              onBlur={() => void handleDetect()}
            />
            <button
              type="button"
              className="rounded-md border px-3 py-2 text-sm"
              onClick={() => void handleDetect()}
            >
              Detect ATS
            </button>
          </div>
          {detectedAts && (
            <p className="text-xs text-muted-foreground">Detected ATS: {detectedAts}</p>
          )}
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="cw-name">
            Company name (optional)
          </label>
          <input
            id="cw-name"
            className="w-full rounded-md border px-3 py-2 text-sm"
            value={companyName}
            onChange={(e) => setCompanyName(e.target.value)}
          />
        </div>
        <div className="space-y-2">
          <label className="text-sm font-medium" htmlFor="cw-keywords">
            Keywords (comma-separated)
          </label>
          <input
            id="cw-keywords"
            className="w-full rounded-md border px-3 py-2 text-sm"
            placeholder="python, backend, remote"
            value={keywords}
            onChange={(e) => setKeywords(e.target.value)}
          />
        </div>
        <button
          type="submit"
          disabled={submitting || !url.trim()}
          className="inline-flex items-center gap-2 rounded-md bg-primary px-4 py-2 text-sm text-primary-foreground disabled:opacity-50"
        >
          {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Plus className="h-4 w-4" />}
          Add watch
        </button>
      </form>

      <section className="space-y-3">
        <h2 className="font-medium">Watched companies</h2>
        {watches.length === 0 ? (
          <p className="text-sm text-muted-foreground">No companies watched yet.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {watches.map((watch) => (
              <li key={watch.id} className="flex items-start justify-between gap-4 p-4">
                <div>
                  <p className="font-medium">{watch.company_name}</p>
                  <p className="text-xs text-muted-foreground">{watch.ats_type}</p>
                  {watch.keywords.length > 0 && (
                    <p className="mt-1 text-sm text-muted-foreground">
                      Keywords: {watch.keywords.join(", ")}
                    </p>
                  )}
                  <Link
                    href={watch.careers_page_url}
                    target="_blank"
                    className="mt-1 inline-flex items-center gap-1 text-xs text-primary"
                  >
                    Careers page <ExternalLink className="h-3 w-3" />
                  </Link>
                </div>
                <button
                  type="button"
                  aria-label="Remove watch"
                  className="rounded-md border p-2 text-muted-foreground hover:text-destructive"
                  onClick={() => void handleRemove(watch.id)}
                >
                  <Trash2 className="h-4 w-4" />
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="space-y-3">
        <h2 className="font-medium">Recent alerts</h2>
        {alerts.length === 0 ? (
          <p className="text-sm text-muted-foreground">No matching roles yet.</p>
        ) : (
          <ul className="divide-y rounded-lg border">
            {alerts.map((alert) => (
              <li key={alert.id} className="flex items-start justify-between gap-4 p-4">
                <div>
                  <p className="font-medium">{alert.job_title}</p>
                  {alert.job_location && (
                    <p className="text-sm text-muted-foreground">{alert.job_location}</p>
                  )}
                  {alert.match_reason && (
                    <p className="mt-1 text-xs text-muted-foreground">{alert.match_reason}</p>
                  )}
                  {alert.apply_url && (
                    <Link
                      href={alert.apply_url}
                      target="_blank"
                      className="mt-1 inline-flex items-center gap-1 text-xs text-primary"
                    >
                      View role <ExternalLink className="h-3 w-3" />
                    </Link>
                  )}
                </div>
                <button
                  type="button"
                  className="text-xs text-muted-foreground underline"
                  onClick={() => void handleDismiss(alert.id)}
                >
                  Dismiss
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  )
}
