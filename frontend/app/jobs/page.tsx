"use client"

import { Suspense, useCallback, useEffect, useState } from "react"
import Link from "next/link"
import { AlertCircle, Loader2, Search, Settings2 } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { getSubscriptionCurrent } from "@/lib/api"
import { isSubscriptionActive } from "@/lib/billing"
import { JobsStaleBanner } from "@/components/jobs/JobsStaleBanner"
import { JobCard } from "@/components/jobs/JobCard"
import { JobCardSkeleton } from "@/components/jobs/JobCardSkeleton"
import {
  listSavedJobs,
  saveJob,
  searchJobs,
  unsaveJob,
  type DatePostedFilter,
  type JobResult,
  type JobSearchFilters,
} from "@/lib/jobs"

const PAGE_SIZE = 20

const DATE_POSTED_OPTIONS: { value: DatePostedFilter; label: string }[] = [
  { value: "any", label: "Any" },
  { value: "24h", label: "Last 24 hours" },
  { value: "week", label: "Past week" },
  { value: "month", label: "Past month" },
]

const EMPLOYMENT_TYPES = [
  { value: "", label: "Any type" },
  { value: "full-time", label: "Full-time" },
  { value: "part-time", label: "Part-time" },
  { value: "contract", label: "Contract" },
  { value: "internship", label: "Internship" },
  { value: "temporary", label: "Temporary" },
]

function JobsPageContent() {
  const { session, status } = useRequireAuth("/jobs")
  const token = session?.backendAccessToken ?? ""

  const [subscribed, setSubscribed] = useState<boolean | null>(null)
  const [role, setRole] = useState("")
  const [location, setLocation] = useState("")
  const [remote, setRemote] = useState(false)
  const [datePosted, setDatePosted] = useState<DatePostedFilter>("any")
  const [salaryMin, setSalaryMin] = useState("")
  const [employmentType, setEmploymentType] = useState("")

  const [jobs, setJobs] = useState<JobResult[]>([])
  const [total, setTotal] = useState(0)
  const [page, setPage] = useState(1)
  const [loading, setLoading] = useState(false)
  const [loadingMore, setLoadingMore] = useState(false)
  const [stale, setStale] = useState(false)
  const [staleMessage, setStaleMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [hasSearched, setHasSearched] = useState(false)
  const [savedIds, setSavedIds] = useState<Set<string>>(new Set())

  const loadSubscription = useCallback(async () => {
    if (!token) return
    try {
      const data = await getSubscriptionCurrent(token)
      const sub = data.subscription
      setSubscribed(!!sub && isSubscriptionActive(sub.status))
    } catch {
      setSubscribed(false)
    }
  }, [token])

  const loadSavedJobs = useCallback(async () => {
    if (!token) return
    try {
      const saved = await listSavedJobs(token)
      setSavedIds(new Set(saved.map((j) => j.id)))
    } catch {
      // Non-fatal — bookmarks still work optimistically
    }
  }, [token])

  useEffect(() => {
    if (token) {
      void loadSubscription()
      void loadSavedJobs()
    }
  }, [token, loadSubscription, loadSavedJobs])

  const buildFilters = (): JobSearchFilters => {
    const filters: JobSearchFilters = {}
    if (remote) filters.remote = true
    const min = parseInt(salaryMin, 10)
    if (!Number.isNaN(min) && min > 0) filters.salary_min_usd = min
    if (employmentType) filters.employment_type = employmentType
    if (datePosted !== "any") filters.date_posted = datePosted
    return filters
  }

  const runSearch = async (nextPage: number, append: boolean) => {
    if (!token || !role.trim()) {
      setError("Enter a role or keyword to search.")
      return
    }

    setError(null)
    if (append) {
      setLoadingMore(true)
    } else {
      setLoading(true)
      setHasSearched(true)
    }

    try {
      const res = await searchJobs(token, {
        query: role.trim(),
        location: location.trim() || null,
        filters: buildFilters(),
        page: nextPage,
        page_size: PAGE_SIZE,
      })

      setJobs((prev) => (append ? [...prev, ...res.jobs] : res.jobs))
      setTotal(res.total)
      setPage(res.page)
      setStale(res.results_may_be_stale)
      setStaleMessage(res.message)
    } catch (e) {
      const err = e as Error & { code?: string }
      if (err.code === "subscription_required") {
        setSubscribed(false)
        setError("Subscription required to search jobs.")
      } else {
        setError(err.message ?? "Search failed.")
      }
      if (!append) {
        setJobs([])
        setTotal(0)
      }
    } finally {
      setLoading(false)
      setLoadingMore(false)
    }
  }

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault()
    void runSearch(1, false)
  }

  const handleLoadMore = () => {
    void runSearch(page + 1, true)
  }

  const handleSaveToggle = async (jobId: string, shouldSave: boolean) => {
    if (!token) return
    try {
      if (shouldSave) {
        await saveJob(token, jobId)
        setSavedIds((prev) => new Set(prev).add(jobId))
      } else {
        await unsaveJob(token, jobId)
        setSavedIds((prev) => {
          const next = new Set(prev)
          next.delete(jobId)
          return next
        })
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update bookmark.")
    }
  }

  if (status === "loading" || !session || subscribed === null) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Loading…
      </div>
    )
  }

  const canLoadMore = jobs.length < total

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
      <div className="max-w-4xl mx-auto px-6 py-12">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 mb-8">
          <div>
            <h1 className="text-2xl font-bold flex items-center gap-2">
              <Search className="w-7 h-7 text-amber-700 dark:text-amber-400" />
              Search jobs
            </h1>
            <p className="text-slate-600 dark:text-slate-400 text-sm mt-1">
              Find roles, check fit, and tailor your resume in one flow.
            </p>
          </div>
          <Link
            href="/jobs/preferences"
            className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2"
          >
            <Settings2 className="w-4 h-4" />
            Preferences
          </Link>
        </div>

        <form
          onSubmit={handleSearch}
          className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-5 space-y-4 mb-8"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block">
              <span className="text-xs text-slate-600 dark:text-slate-400 mb-1 block">Role / keywords</span>
              <input
                value={role}
                onChange={(e) => setRole(e.target.value)}
                placeholder="e.g. Backend engineer Python"
                data-testid="jobs-search-role"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </label>
            <label className="block">
              <span className="text-xs text-slate-600 dark:text-slate-400 mb-1 block">Location</span>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="City, state, or country"
                data-testid="jobs-search-location"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </label>
          </div>

          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <label className="flex items-center gap-2 text-sm text-slate-700 dark:text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={remote}
                onChange={(e) => setRemote(e.target.checked)}
                data-testid="jobs-search-remote"
                className="rounded border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-950 text-amber-700 dark:text-amber-400 focus:ring-amber-400"
              />
              Remote only
            </label>

            <label className="block">
              <span className="text-xs text-slate-600 dark:text-slate-400 mb-1 block">Date posted</span>
              <select
                value={datePosted}
                onChange={(e) => setDatePosted(e.target.value as DatePostedFilter)}
                data-testid="jobs-search-date-posted"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                {DATE_POSTED_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-xs text-slate-600 dark:text-slate-400 mb-1 block">Salary min (USD)</span>
              <input
                type="number"
                min={0}
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value)}
                placeholder="80000"
                data-testid="jobs-search-salary-min"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 placeholder-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400"
              />
            </label>

            <label className="block">
              <span className="text-xs text-slate-600 dark:text-slate-400 mb-1 block">Employment type</span>
              <select
                value={employmentType}
                onChange={(e) => setEmploymentType(e.target.value)}
                data-testid="jobs-search-employment-type"
                className="w-full bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 rounded-lg px-3 py-2 text-sm text-slate-800 dark:text-slate-200 focus:outline-none focus:ring-2 focus:ring-amber-400"
              >
                {EMPLOYMENT_TYPES.map((opt) => (
                  <option key={opt.value || "any"} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </select>
            </label>
          </div>

          <button
            type="submit"
            disabled={loading}
            data-testid="jobs-search-submit"
            className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-6 py-2.5 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 disabled:opacity-40"
          >
            {loading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Searching…
              </>
            ) : (
              <>
                <Search className="w-4 h-4" />
                Search
              </>
            )}
          </button>
        </form>

        {error && (
          <div className="mb-6 flex items-start gap-2 text-red-700 dark:text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
            <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
            {error}
            {error.includes("Subscription") && (
              <Link href="/billing" className="ml-auto text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 shrink-0">
                Upgrade
              </Link>
            )}
          </div>
        )}

        <JobsStaleBanner resultsMayBeStale={stale} message={staleMessage} />

        {loading && (
          <div className="space-y-4" data-testid="jobs-results-loading">
            {Array.from({ length: 3 }).map((_, i) => (
              <JobCardSkeleton key={i} />
            ))}
          </div>
        )}

        {!loading && hasSearched && jobs.length === 0 && !error && (
          <p className="text-center text-slate-600 dark:text-slate-400 py-12">No jobs found. Try different keywords.</p>
        )}

        {!loading && jobs.length > 0 && (
          <div className="space-y-4">
            <p className="text-sm text-slate-600 dark:text-slate-400">
              Showing {jobs.length} of {total} result{total !== 1 ? "s" : ""}
            </p>
            {jobs.map((job, index) => (
              <JobCard
                key={job.id}
                job={job}
                index={index}
                isSubscribed={subscribed}
                accessToken={token}
                saved={savedIds.has(job.id)}
                onSaveToggle={handleSaveToggle}
              />
            ))}

            {canLoadMore && (
              <div className="pt-4 flex justify-center">
                <button
                  type="button"
                  onClick={handleLoadMore}
                  disabled={loadingMore}
                  data-testid="jobs-load-more"
                  className="px-6 py-2.5 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm font-medium hover:border-slate-600 disabled:opacity-40"
                >
                  {loadingMore ? (
                    <span className="inline-flex items-center gap-2">
                      <Loader2 className="w-4 h-4 animate-spin" />
                      Loading…
                    </span>
                  ) : (
                    "Load more"
                  )}
                </button>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  )
}

export default function JobsPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
          Loading…
        </div>
      }
    >
      <JobsPageContent />
    </Suspense>
  )
}
