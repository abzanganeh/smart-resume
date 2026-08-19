import type { ApplicationStatus } from "@/lib/api"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

export type { ApplicationStatus }

export interface ApplicationSummary {
  id: string
  resume_record_id: string | null
  jd_title: string
  jd_company: string
  status: ApplicationStatus
  applied_date: string | null
  follow_up_date: string | null
  archived_at: string | null
  created_at: string
  updated_at: string
}

export interface ApplicationFunnelResponse {
  status_counts: Record<ApplicationStatus, number>
  active_total: number
  archived_total: number
  total: number
  tracker_active_limit: number | null
}

export interface InterviewRound {
  id: string
  round_number: number
  name: string
  format: string
  scheduled_at: string | null
  duration_minutes: number | null
  interviewers: string[]
  notes: string | null
  outcome: string | null
  created_at: string
}

export interface OfferDetail {
  id: string
  base_salary_usd: number | null
  bonus_usd: number | null
  equity_description: string | null
  sign_on_usd: number | null
  benefits: string | null
  location: string | null
  remote: boolean
  start_date: string | null
  response_deadline: string | null
  decision: string | null
  decision_notes: string | null
  created_at: string
}

export interface ApplicationAttachment {
  id: string
  filename: string
  content_type: string
  size_bytes: number
  uploaded_at: string
  download_url?: string
}

export interface TimelineEvent {
  type: string
  at: string
  [key: string]: unknown
}

export interface ApplicationDetail extends ApplicationSummary {
  notes: string | null
  contact_name: string | null
  contact_email: string | null
  job_url: string | null
  rejection_reason: string | null
  rejection_notes: string | null
  status_history: { status: string; at: string }[]
  interview_rounds: InterviewRound[]
  offer_detail: OfferDetail | null
  attachments: ApplicationAttachment[]
  timeline: TimelineEvent[]
  attachment_usage: {
    count: number
    total_bytes: number
    max_count: number
    max_file_bytes: number
    max_total_bytes: number
  }
}

export interface Reminder {
  id: string
  scheduled_at: string
  message: string
  status: string
}

export const PIPELINE_COLUMNS: { key: ApplicationStatus; label: string }[] = [
  { key: "draft", label: "Draft" },
  { key: "applied", label: "Applied" },
  { key: "interviewing", label: "Interviewing" },
  { key: "offer", label: "Offer" },
  { key: "accepted", label: "Accepted" },
  { key: "rejected", label: "Rejected" },
  { key: "withdrawn", label: "Withdrawn" },
]

/**
 * Structured error thrown for non-2xx tracker responses.  Callers can
 * branch on ``code`` (`tracker_limit_reached`, `duplicate_application`,
 * ...) and read the raw ``detail`` payload without re-parsing the
 * message string.
 */
export class TrackerApiError extends Error {
  readonly status: number
  readonly code: string | undefined
  readonly detail: Record<string, unknown> | undefined

  constructor(
    message: string,
    opts: {
      status: number
      code?: string
      detail?: Record<string, unknown>
    },
  ) {
    super(message)
    this.name = "TrackerApiError"
    this.status = opts.status
    this.code = opts.code
    this.detail = opts.detail
  }
}

async function authRequest<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const headers: Record<string, string> = {
    Authorization: `Bearer ${token}`,
    ...(init?.headers as Record<string, string> | undefined),
  }
  if (!(init?.body instanceof FormData)) {
    headers["Content-Type"] = "application/json"
  }
  const res = await fetch(`${BASE}${path}`, { ...init, headers })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body?.detail
    const isObjectDetail = typeof detail === "object" && detail !== null
    const code = isObjectDetail ? (detail.code as string | undefined) : undefined
    const message =
      isObjectDetail
        ? (detail.message as string | undefined) ??
          (detail.detail as string | undefined)
        : typeof detail === "string"
          ? detail
          : undefined
    throw new TrackerApiError(message ?? code ?? `HTTP ${res.status}`, {
      status: res.status,
      code,
      detail: isObjectDetail ? (detail as Record<string, unknown>) : undefined,
    })
  }
  if (res.status === 204) return undefined as T
  return res.json() as Promise<T>
}

export async function listApplications(
  token: string,
  options: { archived?: "true" | "false" | "all" } = {},
): Promise<ApplicationSummary[]> {
  const search = options.archived
    ? `?archived=${encodeURIComponent(options.archived)}`
    : ""
  return authRequest(`/api/applications${search}`, token)
}

export async function getApplicationFunnel(
  token: string,
): Promise<ApplicationFunnelResponse> {
  return authRequest("/api/applications/funnel", token)
}

export async function archiveApplication(
  token: string,
  id: string,
): Promise<ApplicationSummary> {
  return authRequest(`/api/applications/${id}/archive`, token, {
    method: "POST",
  })
}

export async function unarchiveApplication(
  token: string,
  id: string,
): Promise<ApplicationSummary> {
  return authRequest(`/api/applications/${id}/unarchive`, token, {
    method: "POST",
  })
}

export async function getApplication(
  token: string,
  id: string,
): Promise<ApplicationDetail> {
  return authRequest(`/api/applications/${id}`, token)
}

export async function createApplication(
  token: string,
  body: {
    resume_record_id?: string
    jd_title?: string
    jd_company?: string
    job_url?: string
    status?: ApplicationStatus
    /** Set true to bypass duplicate-application 409 checks. */
    confirm_add_duplicate?: boolean
  },
): Promise<ApplicationSummary> {
  return authRequest("/api/applications", token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function patchApplication(
  token: string,
  id: string,
  body: Record<string, unknown>,
): Promise<ApplicationSummary> {
  return authRequest(`/api/applications/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify(body),
  })
}

export async function addInterviewRound(
  token: string,
  applicationId: string,
  body: {
    name: string
    format: string
    scheduled_at?: string
    duration_minutes?: number
    interviewers?: string[]
    notes?: string
    outcome?: string
  },
): Promise<InterviewRound> {
  return authRequest(`/api/applications/${applicationId}/rounds`, token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function upsertOffer(
  token: string,
  applicationId: string,
  body: Record<string, unknown>,
  method: "POST" | "PATCH" = "PATCH",
): Promise<OfferDetail> {
  return authRequest(`/api/applications/${applicationId}/offer`, token, {
    method,
    body: JSON.stringify(body),
  })
}

export async function uploadAttachment(
  token: string,
  applicationId: string,
  file: File,
): Promise<ApplicationAttachment> {
  const form = new FormData()
  form.append("file", file)
  return authRequest(`/api/applications/${applicationId}/attachments`, token, {
    method: "POST",
    body: form,
  })
}

export async function deleteAttachment(
  token: string,
  applicationId: string,
  attachmentId: string,
): Promise<void> {
  await authRequest(
    `/api/applications/${applicationId}/attachments/${attachmentId}`,
    token,
    { method: "DELETE" },
  )
}

export async function listReminders(
  token: string,
  applicationId: string,
): Promise<Reminder[]> {
  return authRequest(`/api/applications/${applicationId}/reminders`, token)
}

export async function createReminder(
  token: string,
  applicationId: string,
  body: { scheduled_at: string; message: string },
): Promise<Reminder> {
  return authRequest(`/api/applications/${applicationId}/reminders`, token, {
    method: "POST",
    body: JSON.stringify(body),
  })
}

export async function deleteReminder(
  token: string,
  applicationId: string,
  reminderId: string,
): Promise<void> {
  await authRequest(
    `/api/applications/${applicationId}/reminders/${reminderId}`,
    token,
    { method: "DELETE" },
  )
}

export function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
