import type {
  DashboardSummaryResponse,
  ResumeListItem,
  ResumeListResponse,
  ResumeRecordStatus,
  ResumeSort,
} from "@/lib/api"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

async function authRequest<T>(
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
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  return res.json() as Promise<T>
}

export async function getDashboardSummary(
  token: string,
): Promise<DashboardSummaryResponse> {
  return authRequest("/api/dashboard/summary", token)
}

export interface ResumeListParams {
  q?: string
  statuses?: ResumeRecordStatus[]
  tag?: string
  date_from?: string
  date_to?: string
  ats_min?: number
  ats_max?: number
  sort?: ResumeSort
  page?: number
  page_size?: number
}

export async function listResumes(
  token: string,
  params: ResumeListParams = {},
): Promise<ResumeListResponse> {
  const qs = new URLSearchParams()
  if (params.q) qs.set("q", params.q)
  if (params.statuses?.length) {
    for (const status of params.statuses) qs.append("status", status)
  }
  if (params.tag) qs.set("tag", params.tag)
  if (params.date_from) qs.set("date_from", params.date_from)
  if (params.date_to) qs.set("date_to", params.date_to)
  if (params.ats_min != null) qs.set("ats_min", String(params.ats_min))
  if (params.ats_max != null) qs.set("ats_max", String(params.ats_max))
  if (params.sort) qs.set("sort", params.sort)
  if (params.page) qs.set("page", String(params.page))
  if (params.page_size) qs.set("page_size", String(params.page_size))
  const query = qs.toString()
  return authRequest(`/api/resumes${query ? `?${query}` : ""}`, token)
}

export async function patchResume(
  token: string,
  id: string,
  body: {
    tags?: string[];
    status?: ResumeRecordStatus;
    display_name?: string | null;
  },
): Promise<ResumeListItem> {
  return authRequest(`/api/resumes/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function deleteResume(token: string, id: string): Promise<void> {
  await authRequest(`/api/resumes/${id}`, token, { method: "DELETE" })
}

export async function duplicateResume(
  token: string,
  id: string,
): Promise<{ session_id: string }> {
  return authRequest(`/api/resumes/${id}/duplicate`, token, { method: "POST" })
}

export async function bulkResumeAction(
  token: string,
  body: {
    action: "delete" | "tag" | "export"
    ids: string[]
    tags?: string[]
  },
): Promise<{
  ok: boolean
  deleted?: number
  tagged?: number
  exports?: Array<{ id: string; title: string; company: string; download_url: string }>
}> {
  return authRequest("/api/resumes/bulk", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export function resumeDownloadUrl(
  id: string,
  format: "pdf" | "docx" | "txt" | "zip",
): string {
  return `${BASE}/api/resumes/${id}/download?format=${format}`
}

function filenameFromContentDisposition(header: string | null): string | null {
  if (!header) return null
  const match = /filename="([^"]+)"/i.exec(header)
  return match?.[1] ?? null
}

export async function downloadResume(
  token: string,
  id: string,
  format: "pdf" | "docx" | "txt" | "zip",
  filename: string,
): Promise<void> {
  const res = await fetch(resumeDownloadUrl(id, format), {
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  const blob = await res.blob()
  const url = URL.createObjectURL(blob)
  const a = document.createElement("a")
  a.href = url
  a.download =
    filenameFromContentDisposition(res.headers.get("Content-Disposition")) ??
    filename
  a.click()
  URL.revokeObjectURL(url)
}
