import { byokHeaders } from "./keyStore";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...byokHeaders(),
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<T>;
}

// ── Sessions ────────────────────────────────────────────────────────────────

export async function createSession(): Promise<{ session_id: string }> {
  return request("/api/sessions", { method: "POST" });
}

export async function checkSession(
  sessionId: string
): Promise<{
  session_id: string;
  ok: boolean;
  resume_raw: string;
  phases: Record<string, { status: string; output: unknown | null }>;
  stale: Record<string, string | null>;
  stale_since?: string | null;
  phase1_complete: boolean;
}> {
  return request(`/api/sessions/${sessionId}`);
}

export async function saveResumeEdits(
  sessionId: string,
  tailoredOutput: TailoredResumeOutput
): Promise<{ ok: boolean }> {
  return request(`/api/sessions/${sessionId}/tailored`, {
    method: "PATCH",
    body: JSON.stringify({ tailored_output: tailoredOutput }),
  });
}

// ── Resume ──────────────────────────────────────────────────────────────────

export async function uploadResumeFile(
  sessionId: string,
  file: File
): Promise<{ parsed: ParsedResume }> {
  const form = new FormData();
  form.append("file", file);
  const res = await fetch(`${BASE}/api/sessions/${sessionId}/resume`, {
    method: "POST",
    // byokHeaders for file uploads (no Content-Type override — browser sets multipart boundary)
    headers: byokHeaders(),
    body: form,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body?.detail ?? `HTTP ${res.status}`);
  }
  return res.json() as Promise<{ parsed: ParsedResume }>;
}

export async function pasteResumeText(
  sessionId: string,
  text: string
): Promise<{ parsed: ParsedResume }> {
  return request<{ parsed: ParsedResume }>(`/api/sessions/${sessionId}/resume/text`, {
    method: "POST",
    body: JSON.stringify({ text }),
  });
}

export async function saveAdditions(
  sessionId: string,
  payload: { claimed_keywords: string[]; extra_notes: string }
): Promise<{ ok: boolean; claimed: number }> {
  return request<{ ok: boolean; claimed: number }>(
    `/api/sessions/${sessionId}/additions`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

export async function saveUserInfo(
  sessionId: string,
  info: UserInfoPayload
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/sessions/${sessionId}/userinfo`, {
    method: "POST",
    body: JSON.stringify(info),
  });
}

export async function submitJD(
  sessionId: string,
  payload: JDPayload
): Promise<{ ok: boolean }> {
  return request<{ ok: boolean }>(`/api/sessions/${sessionId}/jd`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

// ── Phases ──────────────────────────────────────────────────────────────────

export interface PhaseRunScope {
  section: string;
  bullet_index?: number;
  company?: string;
  institution?: string;
  chunk_id?: string;
  chunk_content?: string;
  mode?: "regen" | "add";
}

export async function triggerPhase(
  sessionId: string,
  phase: number,
  options?: { force?: boolean; scope?: PhaseRunScope }
): Promise<{ job_id: string; stream_url: string }> {
  return request(`/api/sessions/${sessionId}/phases/${phase}/run`, {
    method: "POST",
    body: JSON.stringify({
      force: options?.force ?? false,
      scope: options?.scope ?? null,
    }),
  });
}

export function phaseEventsUrl(sessionId: string, phase: number): string {
  return `${BASE}/api/sessions/${sessionId}/phases/${phase}/events`;
}

// ── Tailored resume edits ────────────────────────────────────────────────────

export async function patchTailoredResume(
  sessionId: string,
  patch: Record<string, unknown>
): Promise<{
  version: number;
  snapshot_id: string;
  phase3_versions?: ResumeVersionMeta[];
  stale?: Record<string, string | null>;
}> {
  return request<{
    version: number;
    snapshot_id: string;
    phase3_versions?: ResumeVersionMeta[];
    stale?: Record<string, string | null>;
  }>(
    `/api/sessions/${sessionId}/resume/tailored`,
    { method: "PATCH", body: JSON.stringify(patch) }
  );
}

export async function patchAuditOutput(
  sessionId: string,
  patch: { output?: AuditOutput; summary?: string; overall_score?: number }
): Promise<{ ok: boolean; stale: Record<string, string | null> }> {
  return request(`/api/sessions/${sessionId}/audit`, {
    method: "PATCH",
    body: JSON.stringify(patch),
  });
}

export async function getVersions(sessionId: string) {
  return request<{ versions: ResumeVersionMeta[] }>(
    `/api/sessions/${sessionId}/resume/versions`
  );
}

// ── LLM providers ───────────────────────────────────────────────────────────

export async function getLLMProviders(): Promise<{ providers: LLMProvider[] }> {
  return request("/api/llm/providers");
}

export async function verifyLLMKey(payload: {
  provider: string;
  model: string;
  api_key?: string;
}): Promise<{ valid: boolean; message: string; provider: string; model: string }> {
  const res = await fetch(`${BASE}/api/llm/verify`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return res.json() as Promise<{ valid: boolean; message: string; provider: string; model: string }>;
}

// ── Export ───────────────────────────────────────────────────────────────────

export function exportUrl(
  sessionId: string,
  format: "pdf" | "docx" | "txt"
): string {
  return `${BASE}/api/sessions/${sessionId}/export?format=${format}`;
}

// ── Billing ──────────────────────────────────────────────────────────────────

export async function getBillingPrices(token?: string): Promise<BillingPricesResponse> {
  return request("/api/billing/prices", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

export async function getSubscriptionCurrent(token: string): Promise<SubscriptionCurrentResponse> {
  return request("/api/subscriptions/current", {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function createCheckoutSession(
  token: string,
  payload: { stripe_price_id: string; billing_cycle?: "recurring" | "yearly" },
): Promise<{ checkout_url: string }> {
  return request("/api/subscriptions/checkout", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify(payload),
  })
}

export async function createPortalSession(token: string): Promise<{ portal_url: string }> {
  return request("/api/subscriptions/portal", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function cancelSubscription(token: string): Promise<{ ok: boolean }> {
  return request("/api/subscriptions/cancel", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function resumeSubscription(token: string): Promise<{ ok: boolean }> {
  return request("/api/subscriptions/resume", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function pauseSubscription(token: string): Promise<{ ok: boolean }> {
  return request("/api/subscriptions/pause", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function unpauseSubscription(token: string): Promise<{ ok: boolean }> {
  return request("/api/subscriptions/unpause", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface UserInfoPayload {
  name?: string;
  email?: string;
  phone?: string;
  linkedin?: string;
  github?: string;
  career_stage: "student" | "entry" | "mid" | "senior" | "staff" | "executive";
  target_role: string;
  certifications: string[];
  is_career_transition: boolean;
}

export interface JDPayload {
  jd_text: string;
  jd_url?: string;
  provider?: string;
  model?: string;
}

export interface LLMModelOption {
  id: string;
  label: string;
  note: string;
}

export interface LLMProvider {
  id: string;
  label: string;
  model: string;
  models: LLMModelOption[];
  requires_key: boolean;
  key_url: string;
  has_env_key: boolean;
}

export interface ResumeVersionMeta {
  version: number;
  snapshot_id: string;
  created_at: string;
  label: string;
}

export interface ParsedResume {
  contact: { name: string; email: string; phone?: string; linkedin?: string; github?: string };
  summary?: string;
  skills: string[];
  experience: { title: string; company: string; dates: string; bullets: string[] }[];
  projects: { name: string; description?: string; bullets: string[]; url?: string }[];
  education: { degree: string; institution: string; year?: string; notes?: string }[];
  certifications: string[];
}

export interface Keyword {
  term: string;
  source_sentence: string;
  category: string;
  tier: "must_have" | "nice_to_have";
  reason: string;
  present_in_resume: boolean;
}

export interface KeywordExtractionOutput {
  must_have_keywords: Keyword[];
  nice_to_have_keywords: Keyword[];
  action_verbs: string[];
  seniority_signals: string[];
  boolean_search_terms: string[];
  role_context: { career_level: string; needs_ml_framing: boolean; primary_domain: string };
}

export interface BulletIssue {
  section: string;
  company?: string;
  bullet_index: number;
  original: string;
  issues: string[];
  missing_keywords: string[];
  severity: "low" | "medium" | "high";
}

export interface AuditOutput {
  keyword_coverage: { present: string[]; missing_must_have: string[]; missing_nice_to_have: string[] };
  bullet_issues: BulletIssue[];
  cliches_found: string[];
  irrelevant_sections: string[];
  page_estimate: string;
  page_limit_exceeded: boolean;
  contact_issues: string[];
  overall_score: number;
  summary: string;
}

export interface TailoredExperience {
  title: string;
  company: string;
  dates: string;
  bullets: string[];
  removed_bullets: string[];
  keywords_injected: string[];
}

export interface MetricNeeded {
  section: string;
  company?: string;
  bullet_index: number;
  prompt: string;
}

export interface TailoredEducation {
  degree: string;
  institution: string;
  year: string;
  bullets: string[];
}

export interface TailoredResumeOutput {
  contact: Record<string, string>;
  summary: string;
  skills: string[];
  experience: TailoredExperience[];
  projects: Record<string, unknown>[];
  education: TailoredEducation[];
  certifications: string[];
  rewrite_notes: string[];
  metrics_needed: MetricNeeded[];
  selected_chunks?: Array<{ chunk_id: string; section: string; score: number; tokens: number }>;
  skipped_chunks?: Array<{ chunk_id: string; section: string; score: number; reason: string; content?: string }>;
  retrieval_meta?: Record<string, unknown>;
}

export interface QAItem {
  item: string;
  status: "pass" | "warn" | "fail";
  note: string;
}

export interface BlockingIssue {
  category: "keyword" | "bullet" | "metric" | "format" | "length" | "section";
  description: string;
  suggestion: string;
  impact: "high" | "medium" | "low";
  fix_effort: "one_click" | "user_input" | "manual_rewrite";
}

export interface QAOutput {
  checklist: QAItem[];
  overall_status: "pass" | "warn" | "fail";
  user_action_required: string[];
  /** ATS score (Phase 4) — not AuditOutput.overall_score (Phase 2 audit score). */
  ats_score?: number;
  blocking_issues?: BlockingIssue[];
  score_ceiling?: number;
  quick_wins?: BlockingIssue[];
}

// ── Billing types ─────────────────────────────────────────────────────────────

export interface BillingPlan {
  code: string;
  display_name: string;
  cycle: "daily" | "weekly" | "monthly" | "yearly";
  amount_cents: number;
  trial_days: number | null;
  stripe_price_id: string;
  is_active: boolean;
  features: string[];
}

export interface BillingAddon {
  code: string;
  display_name: string;
  kind: "credit_pack" | "addon_subscription" | "per_resume";
  unit_amount_cents: number;
  credits_granted: number | null;
  stripe_price_id: string;
  billing_cycle_requirement: "yearly" | "monthly" | null;
  is_active: boolean;
}

export interface BillingPricesResponse {
  version: string;
  currency: string;
  plans: BillingPlan[];
  addons: BillingAddon[];
}

export type SubscriptionStatus =
  | "trialing"
  | "active"
  | "cancel_at_period_end"
  | "paused"
  | "cancelled"
  | "expired"
  | "grace";

export interface SubscriptionCurrentResponse {
  /** null when user has no subscription (free tier) */
  subscription: {
    id: string;
    plan: "daily" | "weekly" | "monthly";
    billing_cycle: "recurring" | "yearly";
    status: SubscriptionStatus;
    trial_ends_at: string | null;
    period_start: string;
    period_end: string;
    resumes_used: number;
    resumes_limit: number;
    searches_used: number;
    searches_limit: number;
    cancel_at_period_end: boolean;
    paused_at: string | null;
    pause_resumes_at: string | null;
  } | null;
  /** Free credit balance (relevant when subscription is null) */
  credit_balance: number;
}
