const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type CareerWatchLimits = {
  max_companies: number
  poll_interval_minutes: number
  active_watches: number
}

export type CareerWatchEntry = {
  id: string
  watched_company_id: string
  company_name: string
  careers_page_url: string
  ats_type: string
  keywords: string[]
  is_active: boolean
  created_at: string
}

export type CareerWatchAlert = {
  id: string
  status: string
  match_score: number | null
  match_reason: string | null
  created_at: string
  notified_at: string | null
  job_title: string
  job_location: string
  apply_url: string
}

export type DetectResult = {
  ats_type: string
  board_token: string | null
  careers_page_url: string
  company_name: string | null
}

async function apiFetch<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const resp = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
      ...(init?.headers ?? {}),
    },
  })
  if (!resp.ok) {
    const body = await resp.text()
    throw new Error(body || `Request failed (${resp.status})`)
  }
  if (resp.status === 204) {
    return undefined as T
  }
  return resp.json() as Promise<T>
}

export async function getCareerWatchLimits(token: string): Promise<CareerWatchLimits> {
  return apiFetch("/api/career-watch/limits", token)
}

export async function detectCareersPage(
  token: string,
  careersPageUrl: string,
): Promise<DetectResult> {
  return apiFetch("/api/career-watch/detect", token, {
    method: "POST",
    body: JSON.stringify({ careers_page_url: careersPageUrl }),
  })
}

export async function listCareerWatches(token: string): Promise<CareerWatchEntry[]> {
  return apiFetch("/api/career-watch/watches", token)
}

export async function createCareerWatch(
  token: string,
  body: { careers_page_url: string; company_name?: string; keywords: string[] },
): Promise<CareerWatchEntry> {
  return apiFetch("/api/career-watch/watches", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function updateCareerWatchKeywords(
  token: string,
  watchId: string,
  keywords: string[],
): Promise<CareerWatchEntry> {
  return apiFetch(`/api/career-watch/watches/${watchId}`, token, {
    method: "PATCH",
    body: JSON.stringify({ keywords }),
  })
}

export async function deleteCareerWatch(token: string, watchId: string): Promise<void> {
  await apiFetch(`/api/career-watch/watches/${watchId}`, token, { method: "DELETE" })
}

export async function listCareerAlerts(token: string): Promise<CareerWatchAlert[]> {
  return apiFetch("/api/career-watch/alerts", token)
}

export async function dismissCareerAlert(token: string, alertId: string): Promise<void> {
  await apiFetch(`/api/career-watch/alerts/${alertId}/dismiss`, token, {
    method: "POST",
  })
}
