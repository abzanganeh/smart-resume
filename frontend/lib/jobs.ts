import type { FitAnalysisOutput } from "./api"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function formatJobsApiError(detail: unknown, status: number): string {
  if (typeof detail === "string" && detail.trim()) return detail
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === "string") return item
        if (item && typeof item === "object" && "msg" in item) {
          return String((item as { msg: string }).msg)
        }
        return null
      })
      .filter((msg): msg is string => Boolean(msg))
    if (messages.length > 0) return messages.join("; ")
  }
  if (detail && typeof detail === "object" && "message" in detail) {
    return String((detail as { message: string }).message)
  }
  return `HTTP ${status}`
}

async function jobsRequest<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body?.detail
    const code =
      typeof detail === "object" && detail !== null && !Array.isArray(detail)
        ? (detail as { code?: string }).code
        : undefined
    const err = new Error(formatJobsApiError(detail, res.status)) as Error & {
      code?: string
      status?: number
    }
    err.code = code
    err.status = res.status
    throw err
  }
  if (res.status === 204) {
    return undefined as T
  }
  return res.json() as Promise<T>
}

export type DatePostedFilter = "any" | "24h" | "week" | "month"

export type AlertFrequency = "off" | "daily" | "weekly"

export interface JobSearchFilters {
  remote?: boolean
  salary_min_usd?: number
  employment_type?: string
  date_posted?: DatePostedFilter
}

export interface JobResult {
  id: string
  title: string
  company: string
  location: string
  remote: boolean
  salary_min_usd: number | null
  salary_max_usd: number | null
  employment_type: string
  posted_date: string
  description: string
  apply_url: string
  sources: string[]
  score: number | null
  first_seen_at?: string | null
}

export interface JobSearchResponse {
  jobs: JobResult[]
  total: number
  page: number
  page_size: number
  results_may_be_stale: boolean
  message: string | null
  source?: string
}

export interface JobMatchRequest {
  page?: number
  page_size?: number
}

export type JobSearchMode = "keyword" | "match"

export interface SavedSearch {
  id: string
  name: string
  query: string
  location: string | null
  filters: JobSearchFilters
  alert_frequency: AlertFrequency
  last_alerted_at: string | null
  created_at: string
}

export interface SavedSearchCreate {
  name: string
  query: string
  location?: string | null
  filters?: JobSearchFilters
  alert_frequency?: AlertFrequency
}

export interface JobPreferences {
  blocked_companies: string[]
  default_filters: JobSearchFilters
  preferred_titles?: string[]
  preferred_titles_confirmed?: boolean
  preferred_titles_stale?: boolean
  min_preferred_titles?: number
  max_preferred_titles?: number
}

export interface JobTitleSuggestion {
  title: string
  fit_score: number
  strengths: string[]
  weaknesses: string[]
}

export interface JobTitleSuggestionsResponse {
  suggestions: JobTitleSuggestion[]
  held_titles: string[]
  source: string
  source_hash?: string | null
}

/** Render a monospace fit bar (█ filled, ░ empty). */
export function titleFitBar(score: number, width = 18): string {
  const clamped = Math.max(0, Math.min(100, Math.round(score)))
  const filled = Math.round((clamped / 100) * width)
  return `${"█".repeat(filled)}${"░".repeat(Math.max(0, width - filled))}`
}

export function titleFitLabel(score: number): string {
  return `${Math.round(score)}% fit`
}

export interface PreferredTitlesResponse {
  titles: string[]
  confirmed: boolean
  stale?: boolean
  min_required: number
}

export const MIN_PREFERRED_JOB_TITLES = 1
export const MAX_PREFERRED_JOB_TITLES = 12

export interface JobFitResponse {
  analysis_id: string
  result: FitAnalysisOutput
}

export interface JobSearchRequest {
  query: string
  location?: string | null
  filters?: JobSearchFilters
  page?: number
  page_size?: number
  expand?: boolean
}

export function formatMatchScore(score: number | null | undefined): string | null {
  if (score == null || Number.isNaN(score)) return null
  const pct = score <= 1 ? Math.round(score * 100) : Math.round(score)
  return `${pct}% match`
}

export function formatSalaryRange(job: JobResult): string | null {
  const { salary_min_usd: min, salary_max_usd: max } = job
  if (min == null && max == null) return null
  const fmt = (n: number) =>
    new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      maximumFractionDigits: 0,
    }).format(n)
  if (min != null && max != null) return `${fmt(min)} – ${fmt(max)}`
  if (min != null) return `From ${fmt(min)}`
  return `Up to ${fmt(max!)}`
}

export function formatPostedDate(iso: string): string {
  try {
    const postedAt = new Date(iso)
    const now = Date.now()
    const diffMs = now - postedAt.getTime()
    if (Number.isNaN(diffMs) || diffMs < 0) {
      return postedAt.toLocaleDateString(undefined, {
        month: "short",
        day: "numeric",
        year: "numeric",
      })
    }

    const minutes = Math.floor(diffMs / 60_000)
    if (minutes < 60) return minutes <= 1 ? "1 minute ago" : `${minutes} minutes ago`

    const hours = Math.floor(diffMs / 3_600_000)
    if (hours < 24) return hours === 1 ? "1 hour ago" : `${hours} hours ago`

    const days = Math.floor(diffMs / 86_400_000)
    if (days < 30) return days === 1 ? "1 day ago" : `${days} days ago`

    const months = Math.floor(days / 30)
    if (months < 12) return months === 1 ? "1 month ago" : `${months} months ago`

    const years = Math.floor(months / 12)
    return years === 1 ? "1 year ago" : `${years} years ago`
  } catch {
    return iso
  }
}

/** True when the corpus first indexed this role within the freshness window. */
export function isJobNew(job: JobResult, nowMs: number = Date.now()): boolean {
  if (!job.first_seen_at) return false
  const seen = new Date(job.first_seen_at).getTime()
  if (Number.isNaN(seen)) return false
  const hours = (nowMs - seen) / 3_600_000
  return hours >= 0 && hours <= 48
}

export function summarizeSearchQuery(search: SavedSearch): string {
  const parts = [search.query]
  if (search.location) parts.push(`in ${search.location}`)
  const filters = search.filters ?? {}
  if (filters.remote) parts.push("remote")
  if (filters.salary_min_usd) parts.push(`≥ $${filters.salary_min_usd}`)
  if (filters.employment_type) parts.push(filters.employment_type)
  if (filters.date_posted && filters.date_posted !== "any") {
    parts.push(`posted ${filters.date_posted}`)
  }
  return parts.join(" · ")
}

export function shouldBlurJobCard(index: number, isSubscribed: boolean): boolean {
  return !isSubscribed && index >= 3
}

export function addBlockedCompany(companies: string[], name: string): string[] {
  const trimmed = name.trim()
  if (!trimmed) return companies
  if (companies.some((c) => c.toLowerCase() === trimmed.toLowerCase())) {
    return companies
  }
  return [...companies, trimmed]
}

export function removeBlockedCompany(companies: string[], name: string): string[] {
  return companies.filter((c) => c !== name)
}

export function staleBannerMessage(
  resultsMayBeStale: boolean,
  message?: string | null,
): string | null {
  if (!resultsMayBeStale) return null
  const base = "Results may not be fully up to date"
  const trimmed = message?.trim()
  if (trimmed) return `${base} (${trimmed})`
  return base
}

export async function getJobTitleSuggestions(
  token: string,
): Promise<JobTitleSuggestionsResponse> {
  return jobsRequest("/api/jobs/title-suggestions", token)
}

export async function savePreferredJobTitles(
  token: string,
  titles: string[],
): Promise<PreferredTitlesResponse> {
  return jobsRequest("/api/jobs/preferred-titles", token, {
    method: "PUT",
    body: JSON.stringify({ titles }),
  })
}

export async function searchJobs(
  token: string,
  body: JobSearchRequest,
): Promise<JobSearchResponse> {
  return jobsRequest("/api/jobs/search", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function matchJobs(
  token: string,
  body: JobMatchRequest = {},
): Promise<JobSearchResponse> {
  return jobsRequest("/api/jobs/match", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function getJob(token: string, jobId: string): Promise<JobResult> {
  return jobsRequest(`/api/jobs/${jobId}`, token)
}

export async function fitJob(token: string, jobId: string): Promise<JobFitResponse> {
  return jobsRequest(`/api/jobs/${jobId}/fit`, token, { method: "POST" })
}

export async function saveJob(
  token: string,
  jobId: string,
): Promise<{ id: string; job_id: string }> {
  return jobsRequest(`/api/jobs/${jobId}/save`, token, { method: "POST" })
}

export async function unsaveJob(token: string, jobId: string): Promise<void> {
  await jobsRequest(`/api/jobs/${jobId}/save`, token, { method: "DELETE" })
}

export async function listSavedJobs(token: string): Promise<JobResult[]> {
  return jobsRequest("/api/jobs/saved", token)
}

export async function listSavedSearches(token: string): Promise<SavedSearch[]> {
  return jobsRequest("/api/jobs/saved-searches", token)
}

export async function createSavedSearch(
  token: string,
  body: SavedSearchCreate,
): Promise<SavedSearch> {
  return jobsRequest("/api/jobs/saved-searches", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function updateSavedSearch(
  token: string,
  searchId: string,
  body: Partial<SavedSearchCreate>,
): Promise<SavedSearch> {
  return jobsRequest(`/api/jobs/saved-searches/${searchId}`, token, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function deleteSavedSearch(token: string, searchId: string): Promise<void> {
  await jobsRequest(`/api/jobs/saved-searches/${searchId}`, token, { method: "DELETE" })
}

export async function getJobPreferences(token: string): Promise<JobPreferences> {
  return jobsRequest("/api/jobs/preferences", token)
}

export async function updateJobPreferences(
  token: string,
  body: Partial<JobPreferences>,
): Promise<JobPreferences> {
  return jobsRequest("/api/jobs/preferences", token, {
    method: "PUT",
    body: JSON.stringify(body),
  })
}
