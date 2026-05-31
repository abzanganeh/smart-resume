"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { AlertCircle, ArrowLeft, Loader2, Trash2 } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { BlockedCompaniesSection } from "@/components/jobs/BlockedCompaniesSection"
import {
  createSavedSearch,
  deleteSavedSearch,
  getJobPreferences,
  listSavedSearches,
  summarizeSearchQuery,
  updateJobPreferences,
  updateSavedSearch,
  type AlertFrequency,
  type SavedSearch,
} from "@/lib/jobs"

const MAX_SAVED_SEARCHES = 10
const MAX_ALERT_SEARCHES = 5

const ALERT_OPTIONS: { value: AlertFrequency; label: string }[] = [
  { value: "off", label: "Off" },
  { value: "daily", label: "Daily" },
  { value: "weekly", label: "Weekly" },
]

function PreferencesPageContent() {
  const { session, status } = useRequireAuth("/jobs/preferences")
  const token = session?.backendAccessToken ?? ""

  const [searches, setSearches] = useState<SavedSearch[]>([])
  const [blockedCompanies, setBlockedCompanies] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [savingPrefs, setSavingPrefs] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [newName, setNewName] = useState("")
  const [newQuery, setNewQuery] = useState("")
  const [newLocation, setNewLocation] = useState("")
  const [newAlert, setNewAlert] = useState<AlertFrequency>("off")
  const [creating, setCreating] = useState(false)

  const alertCount = searches.filter((s) => s.alert_frequency !== "off").length

  const loadData = useCallback(async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const [savedSearches, prefs] = await Promise.all([
        listSavedSearches(token),
        getJobPreferences(token),
      ])
      setSearches(savedSearches)
      setBlockedCompanies(prefs.blocked_companies)
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load preferences.")
    } finally {
      setLoading(false)
    }
  }, [token])

  useEffect(() => {
    if (token) void loadData()
  }, [token, loadData])

  const handleCreateSearch = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!token) return
    if (searches.length >= MAX_SAVED_SEARCHES) {
      setError(`Maximum ${MAX_SAVED_SEARCHES} saved searches allowed.`)
      return
    }
    if (newAlert !== "off" && alertCount >= MAX_ALERT_SEARCHES) {
      setError(`Maximum ${MAX_ALERT_SEARCHES} saved searches with alerts enabled.`)
      return
    }

    setCreating(true)
    setError(null)
    try {
      const created = await createSavedSearch(token, {
        name: newName.trim(),
        query: newQuery.trim(),
        location: newLocation.trim() || null,
        alert_frequency: newAlert,
      })
      setSearches((prev) => [created, ...prev])
      setNewName("")
      setNewQuery("")
      setNewLocation("")
      setNewAlert("off")
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to create saved search.")
    } finally {
      setCreating(false)
    }
  }

  const handleAlertChange = async (search: SavedSearch, frequency: AlertFrequency) => {
    if (!token) return
    if (
      frequency !== "off" &&
      search.alert_frequency === "off" &&
      alertCount >= MAX_ALERT_SEARCHES
    ) {
      setError(`Maximum ${MAX_ALERT_SEARCHES} saved searches with alerts enabled.`)
      return
    }

    setError(null)
    try {
      const updated = await updateSavedSearch(token, search.id, {
        alert_frequency: frequency,
      })
      setSearches((prev) => prev.map((s) => (s.id === search.id ? updated : s)))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update alert frequency.")
    }
  }

  const handleDeleteSearch = async (searchId: string) => {
    if (!token) return
    setError(null)
    try {
      await deleteSavedSearch(token, searchId)
      setSearches((prev) => prev.filter((s) => s.id !== searchId))
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to delete saved search.")
    }
  }

  const handleBlockedChange = async (companies: string[]) => {
    if (!token) return
    setBlockedCompanies(companies)
    setSavingPrefs(true)
    setError(null)
    try {
      await updateJobPreferences(token, { blocked_companies: companies })
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update blocked companies.")
      void loadData()
    } finally {
      setSavingPrefs(false)
    }
  }

  if (status === "loading" || !session) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Loading…
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <Link
          href="/jobs"
          className="inline-flex items-center gap-1.5 text-slate-500 hover:text-slate-300 text-sm mb-8"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to job search
        </Link>

        <h1 className="text-2xl font-bold mb-2">Job search preferences</h1>
        <p className="text-slate-400 text-sm mb-8">
          Manage saved searches, alerts, and blocked companies.
        </p>

        {error && (
          <div className="mb-6 flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {error}
          </div>
        )}

        {loading ? (
          <div className="flex justify-center py-16 text-slate-500">
            <Loader2 className="w-6 h-6 animate-spin" />
          </div>
        ) : (
          <div className="space-y-12">
            <section>
              <h2 className="text-lg font-semibold text-white mb-1">Add saved search</h2>
              <p className="text-sm text-slate-400 mb-4">
                Up to {MAX_SAVED_SEARCHES} saved searches ({searches.length}/{MAX_SAVED_SEARCHES}).
                Alerts enabled on up to {MAX_ALERT_SEARCHES} ({alertCount}/{MAX_ALERT_SEARCHES}).
              </p>

              <form
                onSubmit={handleCreateSearch}
                className="rounded-xl border border-slate-800 bg-slate-900 p-5 space-y-4"
              >
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="text-xs text-slate-500 mb-1 block">Name</span>
                    <input
                      value={newName}
                      onChange={(e) => setNewName(e.target.value)}
                      required
                      placeholder="Remote Python roles"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-slate-500 mb-1 block">Query</span>
                    <input
                      value={newQuery}
                      onChange={(e) => setNewQuery(e.target.value)}
                      required
                      placeholder="Python backend engineer"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </label>
                </div>
                <div className="grid gap-4 sm:grid-cols-2">
                  <label className="block">
                    <span className="text-xs text-slate-500 mb-1 block">Location (optional)</span>
                    <input
                      value={newLocation}
                      onChange={(e) => setNewLocation(e.target.value)}
                      placeholder="Remote"
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    />
                  </label>
                  <label className="block">
                    <span className="text-xs text-slate-500 mb-1 block">Alert frequency</span>
                    <select
                      value={newAlert}
                      onChange={(e) => setNewAlert(e.target.value as AlertFrequency)}
                      className="w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
                    >
                      {ALERT_OPTIONS.map((opt) => (
                        <option key={opt.value} value={opt.value}>
                          {opt.label}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                <button
                  type="submit"
                  disabled={creating || searches.length >= MAX_SAVED_SEARCHES}
                  className="px-5 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300 disabled:opacity-40"
                >
                  {creating ? "Saving…" : "Save search"}
                </button>
              </form>
            </section>

            <section>
              <h2 className="text-lg font-semibold text-white mb-4">Saved searches</h2>
              {searches.length === 0 ? (
                <p className="text-sm text-slate-500">No saved searches yet.</p>
              ) : (
                <ul className="space-y-3">
                  {searches.map((search) => (
                    <li
                      key={search.id}
                      className="rounded-xl border border-slate-800 bg-slate-900 p-4"
                      data-testid={`saved-search-${search.id}`}
                    >
                      <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
                        <div>
                          <p className="font-medium text-white">{search.name}</p>
                          <p className="text-sm text-slate-400 mt-0.5">
                            {summarizeSearchQuery(search)}
                          </p>
                          <p className="text-xs text-slate-600 mt-1">
                            Last run:{" "}
                            {search.last_alerted_at
                              ? new Date(search.last_alerted_at).toLocaleString()
                              : "Never"}
                          </p>
                        </div>
                        <div className="flex items-center gap-2 shrink-0">
                          <select
                            value={search.alert_frequency}
                            onChange={(e) =>
                              handleAlertChange(search, e.target.value as AlertFrequency)
                            }
                            aria-label={`Alert frequency for ${search.name}`}
                            className="bg-slate-950 border border-slate-800 rounded-lg px-2 py-1.5 text-xs text-slate-200"
                          >
                            {ALERT_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                          <button
                            type="button"
                            onClick={() => handleDeleteSearch(search.id)}
                            aria-label={`Delete ${search.name}`}
                            className="p-2 rounded-lg text-slate-500 hover:text-red-400 hover:bg-red-950/40"
                          >
                            <Trash2 className="w-4 h-4" />
                          </button>
                        </div>
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </section>

            <BlockedCompaniesSection
              companies={blockedCompanies}
              onChange={handleBlockedChange}
              saving={savingPrefs}
            />
          </div>
        )}
      </div>
    </div>
  )
}

export default function JobPreferencesPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
          Loading…
        </div>
      }
    >
      <PreferencesPageContent />
    </Suspense>
  )
}
