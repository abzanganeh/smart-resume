/**
 * Shared types for the admin panel — mirrors §19.7 backend models.
 */

// ── Session ───────────────────────────────────────────────────────────────────

export interface AdminSession {
  admin_id: string
  email: string
  display_name: string
  role: AdminRole
  /** UNIX ms when the 1-hour TTL expires */
  expires_at: number
  /** Originating IP bound to session */
  ip: string
}

export type AdminRole = "super-admin" | "support-agent" | "read-only-analyst"

// ── Admin login ───────────────────────────────────────────────────────────────

export interface AdminLoginResponse {
  /** Challenge token for the mandatory TOTP step */
  status: "totp_required" | "enrollment_required"
  challenge_token?: string
  expires_in?: number
  must_change_password?: boolean
  enrollment_qr_svg?: string | null
  enrollment_uri?: string | null
  enrollment_secret?: string | null
}

export interface AdminTotpResponse {
  access_token: string
  expires_in: number
  admin: AdminSessionInfo
}

export interface AdminSessionInfo {
  id: string
  email: string
  display_name: string
  role: AdminRole
}

// ── Plans ─────────────────────────────────────────────────────────────────────

export type PlanConfigInterval = "day" | "week" | "month" | "year" | "one_time"

/** Mirrors backend ``PlanConfigOut`` (2026-08 pricing restructure). */
export interface PlanConfig {
  id: string
  code: string
  stripe_price_id: string
  stripe_product_id: string | null
  eligibility: string
  amount_cents: number
  currency: string
  interval: PlanConfigInterval
  is_active: boolean
  effective_from: string
  effective_to: string | null
  created_by_admin_id: string | null
  created_at: string
}

export interface PlanCreatePayload {
  code: string
  stripe_price_id: string
  stripe_product_id?: string | null
  eligibility?: string
  amount_cents: number
  currency?: string
  interval: PlanConfigInterval
}

export interface PlanUpdatePayload {
  stripe_price_id?: string
  stripe_product_id?: string | null
  eligibility?: string
  amount_cents?: number
  currency?: string
  interval?: PlanConfigInterval
  is_active?: boolean
}

export interface PlanAuditedResponse {
  plan: PlanConfig
  audit_log_id: string
}

// ── LLM Config ────────────────────────────────────────────────────────────────

export interface LLMConfig {
  id: string
  tier: "standard" | "better" | "best"
  provider: string
  model_string: string
  fallback_provider: string | null
  fallback_model_string: string | null
  cost_per_resume_usd: number
  phases_enabled: Array<"1" | "2" | "3" | "4" | "fit" | "cover_letter">
  similarity_threshold: number
  active: boolean
  created_by: string
  created_at: string
}

export interface LLMConfigPayload {
  tier: "standard" | "better" | "best"
  provider: string
  model_string: string
  phases_enabled: string[]
  similarity_threshold?: number
  /** @deprecated Not persisted by backend — legacy UI field removed */
  fallback_provider?: string
  fallback_model_string?: string
  cost_per_resume_usd?: number
}

// ── Step LLM pins ───────────────────────────────────────────────────────────

export interface StepLLMConfig {
  step: string
  label: string
  provider: string
  model_string: string
  source: "pin" | "default"
  pin_id: string | null
  is_active: boolean
  notes: string | null
  has_price_row: boolean
  created_at: string | null
  updated_at: string | null
}

export interface StepLLMConfigPayload {
  step: string
  provider: string
  model_string: string
  notes?: string
}

// ── Tier step LLM pins ────────────────────────────────────────────────────────

export type TierStepSource = "tier_pin" | "global_pin" | "default"

export interface TierStepLLMConfig {
  plan_code: string
  step: string
  label: string
  provider: string
  model_string: string
  source: TierStepSource
  pin_id: string | null
  is_active: boolean
  notes: string | null
  has_price_row: boolean
  editable: boolean
  created_at: string | null
  updated_at: string | null
}

export interface TierStepLLMConfigPayload {
  plan_codes: string[]
  step: string
  provider: string
  model_string: string
  notes?: string
}

export const CANONICAL_PLAN_CODES = [
  "free",
  "weekly",
  "monthly_pro",
  "yearly_pro",
  "monthly_plus",
  "yearly_plus",
  "monthly_premium",
  "yearly_premium",
] as const

// ── Feature Flags ─────────────────────────────────────────────────────────────

export interface FeatureFlag {
  id: string
  key: string
  description: string
  enabled: boolean
  rollout_percent: number
  allowlist_emails: string[]
  blocklist_emails: string[]
  updated_by: string
  updated_at: string
}

export interface FeatureFlagPatchPayload {
  enabled?: boolean
  rollout_percent?: number
  allowlist_emails?: string[]
  blocklist_emails?: string[]
}

// ── Announcements ─────────────────────────────────────────────────────────────

export type AnnouncementSeverity = "info" | "warning" | "maintenance"

export interface Announcement {
  id: string
  title: string
  body_markdown: string
  severity: AnnouncementSeverity
  cta_label: string | null
  cta_url: string | null
  starts_at: string
  ends_at: string
  created_by: string
  created_at: string
}

export interface AnnouncementPayload {
  title: string
  body_markdown: string
  severity: AnnouncementSeverity
  cta_label?: string
  cta_url?: string
  starts_at: string
  ends_at: string
}

// ── Users ─────────────────────────────────────────────────────────────────────

export interface AdminUser {
  id: string
  email: string
  display_name: string
  tier: string
  credit_balance: number
  subscription_status: string | null
  stripe_customer_id: string | null
  suspended_at: string | null
  closure_requested_at: string | null
  email_verified_at: string | null
  created_at: string
  last_login_at: string | null
}

export interface AdminUserDetail extends AdminUser {
  resume_count: number
  credit_transactions: CreditTransaction[]
  login_history: LoginHistoryEntry[]
  signup_ip?: string | null
  signup_abuse_review_flag?: string | null
  last_login_ip?: string | null
  auth_provider?: string
}

export interface CreditTransaction {
  id: string
  amount: number
  reason: string
  initiated_by: string
  admin_id: string | null
  created_at: string
}

export interface LoginHistoryEntry {
  id: string
  event: string
  ip: string
  user_agent: string
  created_at: string
}

export interface UserListResponse {
  users: AdminUser[]
  total: number
  page: number
  per_page: number
}

export interface CreditAdjustPayload {
  amount: number
  reason: string
}

// ── Promo & free grant ────────────────────────────────────────────────────────

export type PromoGrantType =
  | "extra_credits"
  | "tier_override"
  | "feature_unlock"
  | "price_discount"

export interface PromoCode {
  id: string
  code: string
  grant_type: PromoGrantType
  payload: Record<string, unknown>
  max_redemptions: number | null
  redemption_count: number
  expires_at: string | null
  is_active: boolean
  is_redeemable: boolean
  offer_summary: string
  remaining_redemptions: number | null
  created_by_admin_id: string | null
  restricted_user_id: string | null
  created_at: string
}

export interface PromoCodeCreatePayload {
  code: string
  grant_type: PromoGrantType
  payload: Record<string, unknown>
  max_redemptions?: number | null
  expires_at?: string | null
  restricted_user_id?: string | null
}

export interface PromoCodeUpdatePayload {
  max_redemptions?: number | null
  expires_at?: string | null
  is_active?: boolean
}

export interface PromoRedemption {
  id: string
  promo_code_id: string
  user_id: string
  redeemed_at: string
}

export interface FreeGrant {
  amount: number
}

export interface PromoAuditedResponse {
  audit_log_id: string
  promo_code: PromoCode
}

export interface FreeGrantAuditedResponse {
  audit_log_id: string
  free_grant: FreeGrant
}

// ── Refunds ───────────────────────────────────────────────────────────────────

export interface RefundRequest {
  id: string
  user_id: string
  user_email: string
  amount_usd: number
  reason: string
  stripe_charge_id: string
  status: "pending" | "approved" | "denied"
  created_at: string
  resolved_at: string | null
  resolved_by: string | null
  deny_reason: string | null
}

export interface RefundListResponse {
  refunds: RefundRequest[]
  total: number
}

// ── Reports ───────────────────────────────────────────────────────────────────

export interface ActivityMetrics {
  date: string
  dau: number
  wau: number
  mau: number
  new_registrations: number
}

export interface FunnelMetrics {
  registered: number
  email_verified: number
  first_build: number
  first_export: number
  subscribed: number
}

export interface RevenueByPlan {
  plan: string
  revenue_usd: number
  subscribers: number
}

export interface LLMCostMargin {
  date: string
  tier: string
  cost_usd: number
  revenue_usd: number
  margin_usd: number
  volume: number
}

export interface ChurnMetrics {
  date: string
  plan: string
  churn_rate: number
}

// ── System Health ─────────────────────────────────────────────────────────────

export interface SystemHealth {
  stripe_webhook_success_rate: number
  hirebase_circuit_breaker: "closed" | "open" | "half-open"
  apify_queue_depth: number
  resend_delivery_success_rate: number
  error_rate_24h: number
  llm_latency: {
    standard: LatencyPercentiles
    better: LatencyPercentiles
    best: LatencyPercentiles
  }
}

export interface LatencyPercentiles {
  p50: number
  p95: number
  p99: number
}

// ── Audit Log ─────────────────────────────────────────────────────────────────

export interface AuditLogEntry {
  id: string
  admin_id: string
  admin_email: string
  action: string
  target_type: string
  target_id: string
  old_value: unknown | null
  new_value: unknown | null
  request_ip: string
  created_at: string
}

export interface AuditLogResponse {
  entries: AuditLogEntry[]
  total: number
}

// ── Write action audit response ───────────────────────────────────────────────

export interface AuditedResponse<T = unknown> {
  data: T
  audit_log_id: string
}
