/**
 * Typed fetch wrappers for all admin API endpoints (§19.7).
 *
 * Every mutating call returns an `AuditedResponse<T>` containing
 * `audit_log_id` so the UI can display the audit toast.
 */

import type {
  AdminLoginResponse,
  AdminTotpResponse,
  AuditedResponse,
  PlanConfig,
  PlanCreatePayload,
  LLMConfig,
  LLMConfigPayload,
  FeatureFlag,
  FeatureFlagPatchPayload,
  Announcement,
  AnnouncementPayload,
  AdminUserDetail,
  UserListResponse,
  CreditAdjustPayload,
  RefundListResponse,
  ActivityMetrics,
  FunnelMetrics,
  RevenueByPlan,
  LLMCostMargin,
  ChurnMetrics,
  SystemHealth,
  AuditLogResponse,
  LLMAddonPricing,
} from "./types"

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

// ── Internal helpers ──────────────────────────────────────────────────────────

function adminHeaders(token: string): HeadersInit {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.detail?.code ?? body?.detail ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

async function req<T>(
  path: string,
  token: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    credentials: "include",
    headers: { ...adminHeaders(token), ...(init?.headers ?? {}) },
    ...init,
  })
  if (!res.ok) {
    const msg = await parseError(res)
    throw new Error(msg)
  }
  return res.json() as Promise<T>
}

// ── Auth ──────────────────────────────────────────────────────────────────────

export async function adminLogin(
  email: string,
  password: string,
): Promise<AdminLoginResponse> {
  const res = await fetch(`${BASE}/api/admin/auth/login`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email, password }),
  })
  if (!res.ok) {
    const msg = await parseError(res)
    throw new Error(msg)
  }
  const data = (await res.json()) as Partial<AdminLoginResponse>
  if (data.status === "enrollment_required") {
    return {
      status: "enrollment_required",
      enrollment_qr_svg: data.enrollment_qr_svg ?? null,
      enrollment_uri: data.enrollment_uri ?? null,
      enrollment_secret: data.enrollment_secret ?? null,
    }
  }
  return {
    status: "totp_required",
    challenge_token: data.challenge_token ?? "",
    expires_in: data.expires_in ?? 300,
  }
}

export async function adminVerifyTotp(
  challenge_token: string,
  code: string,
): Promise<AdminTotpResponse> {
  const res = await fetch(`${BASE}/api/admin/auth/2fa/verify`, {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ challenge_token, code }),
  })
  if (!res.ok) {
    const msg = await parseError(res)
    throw new Error(msg)
  }
  return res.json() as Promise<AdminTotpResponse>
}

export async function adminLogout(token: string): Promise<void> {
  await fetch(`${BASE}/api/admin/auth/logout`, {
    method: "POST",
    credentials: "include",
    headers: adminHeaders(token),
  })
}

// ── Plans ─────────────────────────────────────────────────────────────────────

export async function getAdminPlans(
  token: string,
): Promise<{ plans: PlanConfig[]; addon_pricing: LLMAddonPricing }> {
  return req(`/api/admin/plans`, token)
}

export async function createAdminPlan(
  token: string,
  payload: PlanCreatePayload,
): Promise<AuditedResponse<PlanConfig>> {
  return req(`/api/admin/plans`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function patchAdminPlan(
  token: string,
  id: string,
  payload: Partial<PlanCreatePayload>,
): Promise<AuditedResponse<PlanConfig>> {
  return req(`/api/admin/plans/${id}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export async function getAdminPlansHistory(
  token: string,
): Promise<PlanConfig[]> {
  return req(`/api/admin/plans/history`, token)
}

export async function updateAdminAddonPricing(
  token: string,
  payload: Partial<LLMAddonPricing>,
): Promise<AuditedResponse<LLMAddonPricing>> {
  return req(`/api/admin/plans/addon-pricing`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

// ── LLM Config ────────────────────────────────────────────────────────────────

export async function getAdminLLMConfigs(
  token: string,
): Promise<{ configs: LLMConfig[]; similarity_threshold: number }> {
  return req(`/api/admin/llm`, token)
}

export async function createAdminLLMConfig(
  token: string,
  payload: LLMConfigPayload,
): Promise<AuditedResponse<LLMConfig>> {
  return req(`/api/admin/llm`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function getAdminLLMHistory(
  token: string,
): Promise<LLMConfig[]> {
  return req(`/api/admin/llm/history`, token)
}

export async function updateSimilarityThreshold(
  token: string,
  threshold: number,
): Promise<AuditedResponse<{ similarity_threshold: number }>> {
  return req(`/api/admin/llm/similarity-threshold`, token, {
    method: "PATCH",
    body: JSON.stringify({ threshold }),
  })
}

// ── Feature Flags ─────────────────────────────────────────────────────────────

export async function getAdminFeatureFlags(
  token: string,
): Promise<{ flags: FeatureFlag[] }> {
  return req(`/api/admin/feature-flags`, token)
}

export async function createAdminFeatureFlag(
  token: string,
  payload: { key: string; description: string; enabled: boolean },
): Promise<AuditedResponse<FeatureFlag>> {
  return req(`/api/admin/feature-flags`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function patchAdminFeatureFlag(
  token: string,
  key: string,
  payload: FeatureFlagPatchPayload,
): Promise<AuditedResponse<FeatureFlag>> {
  return req(`/api/admin/feature-flags/${key}`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

// ── Announcements ─────────────────────────────────────────────────────────────

export async function getAdminAnnouncements(
  token: string,
): Promise<{ announcements: Announcement[] }> {
  return req(`/api/admin/announcements`, token)
}

export async function createAdminAnnouncement(
  token: string,
  payload: AnnouncementPayload,
): Promise<AuditedResponse<Announcement>> {
  return req(`/api/admin/announcements`, token, {
    method: "POST",
    body: JSON.stringify(payload),
  })
}

export async function deleteAdminAnnouncement(
  token: string,
  id: string,
): Promise<AuditedResponse<{ deleted: true }>> {
  return req(`/api/admin/announcements/${id}`, token, { method: "DELETE" })
}

// ── Users ─────────────────────────────────────────────────────────────────────

export async function getAdminUsers(
  token: string,
  params: { q?: string; page?: number; per_page?: number },
): Promise<UserListResponse> {
  const qs = new URLSearchParams()
  if (params.q) qs.set("q", params.q)
  if (params.page) qs.set("page", String(params.page))
  if (params.per_page) qs.set("per_page", String(params.per_page))
  return req(`/api/admin/users?${qs}`, token)
}

export async function getAdminUserDetail(
  token: string,
  userId: string,
): Promise<AdminUserDetail> {
  return req(`/api/admin/users/${userId}`, token)
}

export async function adjustUserCredits(
  token: string,
  userId: string,
  payload: CreditAdjustPayload,
): Promise<AuditedResponse<{ new_balance: number }>> {
  return req(`/api/admin/users/${userId}/credits`, token, {
    method: "PATCH",
    body: JSON.stringify(payload),
  })
}

export async function suspendUser(
  token: string,
  userId: string,
  reason: string,
): Promise<AuditedResponse<{ suspended_at: string }>> {
  return req(`/api/admin/users/${userId}/suspend`, token, {
    method: "PATCH",
    body: JSON.stringify({ reason }),
  })
}

export async function unsuspendUser(
  token: string,
  userId: string,
): Promise<AuditedResponse<{ suspended_at: null }>> {
  return req(`/api/admin/users/${userId}/unsuspend`, token, {
    method: "PATCH",
    body: JSON.stringify({}),
  })
}

export async function triggerUserExport(
  token: string,
  userId: string,
): Promise<AuditedResponse<{ export_id: string }>> {
  return req(`/api/admin/users/${userId}/export`, token, { method: "POST", body: JSON.stringify({}) })
}

export async function closeUserAccount(
  token: string,
  userId: string,
): Promise<AuditedResponse<{ closure_requested_at: string }>> {
  return req(`/api/admin/users/${userId}/close`, token, {
    method: "POST",
    body: JSON.stringify({}),
  })
}

export async function deleteUserImmediately(
  token: string,
  userId: string,
): Promise<AuditedResponse<{ deleted: true }>> {
  return req(`/api/admin/users/${userId}/delete-immediately`, token, {
    method: "POST",
    body: JSON.stringify({}),
  })
}

// ── Refunds ───────────────────────────────────────────────────────────────────

export async function getAdminRefunds(
  token: string,
  status = "pending",
): Promise<RefundListResponse> {
  return req(`/api/admin/refunds?status=${status}`, token)
}

export async function approveRefund(
  token: string,
  refundId: string,
): Promise<AuditedResponse<{ refund_id: string }>> {
  return req(`/api/admin/refunds/${refundId}/approve`, token, {
    method: "POST",
    body: JSON.stringify({}),
  })
}

export async function denyRefund(
  token: string,
  refundId: string,
  reason: string,
): Promise<AuditedResponse<{ refund_id: string }>> {
  return req(`/api/admin/refunds/${refundId}/deny`, token, {
    method: "POST",
    body: JSON.stringify({ reason }),
  })
}

// ── Reports ───────────────────────────────────────────────────────────────────

export async function getActivityMetrics(
  token: string,
  params: { from: string; to: string },
): Promise<{ metrics: ActivityMetrics[] }> {
  const qs = new URLSearchParams(params)
  return req(`/api/admin/reports/activity?${qs}`, token)
}

export async function getFunnelMetrics(
  token: string,
  params: { from: string; to: string },
): Promise<FunnelMetrics> {
  const qs = new URLSearchParams(params)
  return req(`/api/admin/reports/funnel?${qs}`, token)
}

export async function getRevenueByPlan(
  token: string,
  params: { from: string; to: string },
): Promise<{ revenue: RevenueByPlan[] }> {
  const qs = new URLSearchParams(params)
  return req(`/api/admin/reports/revenue?${qs}`, token)
}

export async function getLLMCostMargin(
  token: string,
  params: { from: string; to: string },
): Promise<{ data: LLMCostMargin[] }> {
  const qs = new URLSearchParams(params)
  return req(`/api/admin/reports/llm-cost?${qs}`, token)
}

export async function getChurnMetrics(
  token: string,
  params: { from: string; to: string },
): Promise<{ data: ChurnMetrics[] }> {
  const qs = new URLSearchParams(params)
  return req(`/api/admin/reports/churn?${qs}`, token)
}

export async function exportReportCSV(
  token: string,
  report: string,
  params: { from: string; to: string },
): Promise<Blob> {
  const qs = new URLSearchParams({ ...params, report })
  const res = await fetch(`${BASE}/api/admin/reports/export?${qs}`, {
    credentials: "include",
    headers: { Authorization: `Bearer ${token}` },
  })
  if (!res.ok) throw new Error(`HTTP ${res.status}`)
  return res.blob()
}

// ── System Health ─────────────────────────────────────────────────────────────

export async function getSystemHealth(token: string): Promise<SystemHealth> {
  return req(`/api/admin/system/health`, token)
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

export async function getAuditLog(
  token: string,
  params: {
    actor?: string
    action?: string
    target_type?: string
    from?: string
    to?: string
    page?: number
    per_page?: number
  },
): Promise<AuditLogResponse> {
  const qs = new URLSearchParams()
  Object.entries(params).forEach(([k, v]) => v !== undefined && qs.set(k, String(v)))
  return req(`/api/admin/audit?${qs}`, token)
}
