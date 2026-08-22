import { byokHeaders } from "./keyStore";
import { getSession } from "next-auth/react";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Structured API error that preserves the backend error code for UI branching. */
export class ApiError extends Error {
  code: string | undefined;
  status: number;
  constructor(message: string, status: number, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

function formatApiErrorMessage(
  detail: unknown,
  status: number,
): { message: string; code?: string } {
  if (typeof detail === "string") {
    return { message: detail };
  }
  if (detail && typeof detail === "object") {
    const d = detail as Record<string, unknown>;
    const code = typeof d.code === "string" ? d.code : undefined;
    const candidate = d.message ?? d.error;
    if (typeof candidate === "string") {
      return { message: candidate, code };
    }
    if (code === "insufficient_credits") {
      const action = typeof d.action === "string" ? d.action : undefined;
      if (action === "ats_recalc") {
        return {
          code,
          message:
            "You're out of credits. ATS score recalculation costs 1 credit.",
        };
      }
      return {
        code,
        message: "You're out of credits. Subscribe from Billing to keep going.",
      };
    }
    if (code === "subscription_required") {
      return { code, message: "This feature requires an active subscription." };
    }
    if (typeof code === "string") {
      return { message: code, code };
    }
    return { message: JSON.stringify(detail) };
  }
  return { message: `HTTP ${status}` };
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  // Attach the NextAuth bearer token on every API call when a session exists.
  // Falls back gracefully for anonymous (unauthenticated) usage.
  let authHeader: Record<string, string> = {};
  try {
    const nextAuthSession = await getSession();
    const token = (nextAuthSession as { backendAccessToken?: string } | null)
      ?.backendAccessToken;
    if (token) {
      authHeader = { Authorization: `Bearer ${token}` };
    }
  } catch {
    // getSession() may throw during SSR or in non-browser contexts; ignore.
  }

  const res = await fetch(`${BASE}${path}`, {
    headers: {
      "Content-Type": "application/json",
      ...byokHeaders(),
      ...authHeader,
      ...(init?.headers ?? {}),
    },
    ...init,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const { message, code } = formatApiErrorMessage(body?.detail, res.status);
    throw new ApiError(message, res.status, code);
  }
  return res.json() as Promise<T>;
}

// ── Sessions ────────────────────────────────────────────────────────────────

export async function createSession(): Promise<{ session_id: string }> {
  return request("/api/sessions", { method: "POST" });
}

export interface BulletFixPayload {
  original: string;
  suggestion: string;
}

export interface ApprovedMetric {
  scope: string;
  metric: string;
  source_note?: string;
}

export interface SuspiciousMetric {
  scope: string;
  bullet: string;
  reason: "round_percentage" | "dollar_claim" | "stacked_metrics" | "no_source";
}

export async function checkSession(
  sessionId: string
): Promise<{
  session_id: string;
  ok: boolean;
  resume_raw: string;
  has_jd?: boolean;
  export_company?: string | null;
  phases: Record<string, { status: string; output: unknown | null }>;
  cover_letter?: CoverLetterOutput | null;
  stale: Record<string, string | null>;
  stale_since?: string | null;
  phase1_complete: boolean;
  has_user_info?: boolean;
  resume_parsed?: ParsedResume | null;
  user_claimed_keywords: string[];
  user_extra_notes: string;
  bullet_fixes: BulletFixPayload[];
  approved_metrics: ApprovedMetric[];
}> {
  return request(`/api/sessions/${sessionId}`);
}

export async function saveApprovedMetrics(
  sessionId: string,
  metrics: ApprovedMetric[]
): Promise<{ ok: boolean; count: number }> {
  return request(`/api/sessions/${sessionId}/approved-metrics`, {
    method: "PATCH",
    body: JSON.stringify({ approved_metrics: metrics }),
  });
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

  let authHeader: Record<string, string> = {};
  try {
    const nextAuthSession = await getSession();
    const token = (nextAuthSession as { backendAccessToken?: string } | null)
      ?.backendAccessToken;
    if (token) authHeader = { Authorization: `Bearer ${token}` };
  } catch {
    // ignore
  }

  const res = await fetch(`${BASE}/api/sessions/${sessionId}/resume`, {
    method: "POST",
    // No Content-Type override — browser sets multipart boundary automatically.
    headers: { ...byokHeaders(), ...authHeader },
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
  payload: { claimed_keywords: string[]; extra_notes: string; bullet_fixes?: BulletFixPayload[] }
): Promise<{ ok: boolean; claimed: number }> {
  return request<{ ok: boolean; claimed: number }>(
    `/api/sessions/${sessionId}/additions`,
    { method: "PATCH", body: JSON.stringify(payload) }
  );
}

export async function suggestBulletFixes(
  sessionId: string,
  indices: number[],
): Promise<{ fixes: { index: number; suggestion: string }[] }> {
  return request(`/api/sessions/${sessionId}/audit/suggest-bullet-fixes`, {
    method: "POST",
    body: JSON.stringify({ indices }),
  });
}

export async function saveUserInfo(
  sessionId: string,
  info: UserInfoPayload,
  jdId?: string,
): Promise<{ ok: boolean }> {
  const qs = jdId ? `?jd_id=${encodeURIComponent(jdId)}` : "";
  return request<{ ok: boolean }>(`/api/sessions/${sessionId}/userinfo${qs}`, {
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

export async function restoreResumeVersion(
  sessionId: string,
  snapshotId: string,
): Promise<{
  version: number;
  snapshot_id: string;
  tailored_output: TailoredResumeOutput;
  stale?: Record<string, string | null>;
}> {
  return request(`/api/sessions/${sessionId}/resume/versions/${snapshotId}/restore`, {
    method: "POST",
  });
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

export interface FlintHandoffResponse {
  token: string;
  expires_in: number;
}

/** Mint a single-use token for Flint to import this session's tailored context. */
export async function createFlintHandoff(
  sessionId: string,
): Promise<FlintHandoffResponse> {
  return request<FlintHandoffResponse>(
    `/api/sessions/${sessionId}/flint-handoff`,
    { method: "POST" },
  );
}

// ── Cover letter ─────────────────────────────────────────────────────────────

export type CoverLetterTone = "formal" | "balanced" | "warm";

export interface CoverLetterOutput {
  body_markdown: string;
  body_plain: string;
  word_count: number;
  tone: CoverLetterTone;
  keywords_used: string[];
}

export async function fetchCoverLetter(sessionId: string): Promise<CoverLetterOutput> {
  return request(`/api/sessions/${sessionId}/cover-letter`);
}

export function coverLetterExportUrl(
  sessionId: string,
  format: "pdf" | "docx" | "txt",
): string {
  return `${BASE}/api/sessions/${sessionId}/cover-letter/export?format=${format}`;
}

export async function streamCoverLetterGeneration(
  sessionId: string,
  payload: { tone: CoverLetterTone; custom_hook?: string },
  accessToken: string,
  onEvent: (event: import("./sse").SSEEvent) => void,
): Promise<void> {
  const res = await fetch(`${BASE}/api/sessions/${sessionId}/cover-letter`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${accessToken}`,
      ...byokHeaders(),
    },
    body: JSON.stringify(payload),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail = body?.detail;
    const code = typeof detail === "object" ? detail?.code : detail;
    throw new Error(code ?? detail ?? `HTTP ${res.status}`);
  }

  if (!res.body) {
    throw new Error("No response stream");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let streamError: Error | null = null;

  const consumeChunk = (chunk: string) => {
    for (const line of chunk.split("\n")) {
      if (!line.startsWith("data: ")) continue;
      const parsed = JSON.parse(line.slice(6)) as import("./sse").SSEEvent;
      onEvent(parsed);
      if (parsed.event === "error") {
        streamError = new Error(parsed.message ?? "Generation failed.");
      }
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      if (buffer.trim()) {
        consumeChunk(buffer);
      }
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    const parts = buffer.split("\n\n");
    buffer = parts.pop() ?? "";

    for (const part of parts) {
      consumeChunk(part);
    }

    if (streamError) {
      throw streamError;
    }
  }

  if (streamError) {
    throw streamError;
  }
}

// ── Billing ──────────────────────────────────────────────────────────────────

export async function getBillingPrices(token?: string): Promise<BillingPricesResponse> {
  return request("/api/billing/prices", {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  })
}

const SUBSCRIPTION_CACHE_TTL_MS = 60_000
let subscriptionCache: {
  token: string
  data: SubscriptionCurrentResponse
  fetchedAt: number
} | null = null
let subscriptionInflight: Promise<SubscriptionCurrentResponse> | null = null
let subscriptionBlockedUntil = 0

async function fetchSubscriptionCurrentRaw(
  token: string,
): Promise<SubscriptionCurrentResponse> {
  return request("/api/subscriptions/current", {
    headers: { Authorization: `Bearer ${token}` },
  })
}

/** Drop cached subscription/credit snapshot (e.g. after a credit-consuming action). */
export function invalidateSubscriptionCache(): void {
  subscriptionCache = null
  subscriptionInflight = null
}

/** Cached, single-flight subscription snapshot for nav widgets. */
export async function getSubscriptionCurrent(
  token: string,
): Promise<SubscriptionCurrentResponse> {
  const now = Date.now()
  if (now < subscriptionBlockedUntil) {
    if (subscriptionCache?.token === token) return subscriptionCache.data
    throw new ApiError("rate_limited", 429, "rate_limited")
  }

  if (
    subscriptionCache?.token === token &&
    now - subscriptionCache.fetchedAt < SUBSCRIPTION_CACHE_TTL_MS
  ) {
    return subscriptionCache.data
  }

  if (subscriptionInflight) return subscriptionInflight

  subscriptionInflight = fetchSubscriptionCurrentRaw(token)
    .then((data) => {
      subscriptionCache = { token, data, fetchedAt: Date.now() }
      return data
    })
    .catch((err) => {
      if (err instanceof ApiError && err.status === 429) {
        subscriptionBlockedUntil = Date.now() + 60_000
      }
      throw err
    })
    .finally(() => {
      subscriptionInflight = null
    })

  return subscriptionInflight
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

export interface PromoRedeemResponse {
  ok: boolean
  idempotent: boolean
  promo_code_id: string
  grant_type: string
  payload: Record<string, unknown>
  redemption_id: string
  credit_transaction_id: string | null
}

export async function redeemPromoCode(
  token: string,
  code: string,
): Promise<PromoRedeemResponse> {
  return request("/api/promo/redeem", {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: JSON.stringify({ code }),
  })
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface UserInfoPayload {
  name?: string;
  email?: string;
  phone?: string;
  linkedin?: string;
  github?: string;
  location?: string;
  website?: string;
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
  jd_id?: string;
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
  contact: {
    name: string;
    email: string;
    phone?: string;
    linkedin?: string;
    github?: string;
    location?: string;
    website?: string;
  };
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
  unverified_metrics?: SuspiciousMetric[];
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

export interface IssueAnchor {
  section: "experience" | "projects" | "education";
  entry_index: number;
  bullet_index?: number;
}

export interface BlockingIssue {
  category: "keyword" | "bullet" | "metric" | "format" | "length" | "section";
  description: string;
  suggestion: string;
  impact: "high" | "medium" | "low";
  fix_effort: "one_click" | "user_input" | "manual_rewrite";
  anchor?: IssueAnchor | null;
}

export interface ScoreAxis {
  key: string;
  label: string;
  score: number;
  max: number;
  status: "pass" | "warn" | "fail";
  summary: string;
  issues: string[];
}

export type RankLabel = "needs_work" | "fair" | "good" | "great" | "excellent";

export interface NarrativeCategorySummary {
  category_key: string;
  label: string;
  severity: "minor" | "urgent" | "critical";
  issue_count: number;
  why_it_matters: string;
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
  /** Deterministic per-axis breakdown — populated server-side by phase4_score. */
  score_axes?: ScoreAxis[];
  missing_keywords?: string[];
  single_section_keywords?: string[];
  rank_label?: RankLabel;
  headline?: string;
  category_summaries?: NarrativeCategorySummary[];
}

export interface CheckupResponse {
  result: QAOutput;
}

export async function runCheckup(params: {
  jdText: string;
  jobTitle?: string;
  resumeText?: string;
  file?: File | null;
}): Promise<QAOutput> {
  const form = new FormData();
  form.append("jd_text", params.jdText.trim());
  if (params.jobTitle?.trim()) {
    form.append("job_title", params.jobTitle.trim());
  }
  if (params.resumeText?.trim()) {
    form.append("resume_text", params.resumeText.trim());
  }
  if (params.file) {
    form.append("file", params.file);
  }

  const res = await fetch(`${BASE}/api/checkup`, {
    method: "POST",
    body: form,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const { message, code } = formatApiErrorMessage(body?.detail ?? body, res.status);
    throw new ApiError(message, res.status, code);
  }

  const data = (await res.json()) as CheckupResponse;
  return data.result;
}

// ── Fit analysis ─────────────────────────────────────────────────────────────

export type FitLabel = "strong" | "good" | "partial" | "weak"

export interface SectionFit {
  section_type: string
  match_score: number
  matched_items: string[]
  missing_items: string[]
}

export interface FitAnalysisOutput {
  overall_fit_score: number
  fit_label: FitLabel
  section_fits: SectionFit[]
  key_gaps: string[]
  key_strengths: string[]
  recommendation: string
  should_apply: boolean
  suggested_master_resume_edits: string[]
}

export interface FitHistoryItem {
  id: string
  jd_hash: string
  overall_fit_score: number
  fit_label: FitLabel
  created_at: string
}

export interface FitHistoryResponse {
  items: FitHistoryItem[]
  total: number
  page: number
  page_size: number
}

export interface FitDetailResponse {
  id: string
  jd_hash: string
  jd_text: string
  result: FitAnalysisOutput
  created_at: string
}

export async function fetchJdFromUrl(
  token: string,
  jdUrl: string,
): Promise<string> {
  const res = await fetch(`${BASE}/api/fit/fetch-jd`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ jd_url: jdUrl }),
  })
  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    throw new Error(body?.detail ?? `HTTP ${res.status}`)
  }
  const body = (await res.json()) as { jd_text: string }
  return body.jd_text
}

export async function streamFitAnalysis(
  token: string,
  payload: { jd_text?: string; jd_url?: string; file?: File },
  onEvent: (event: import("./sse").SSEEvent) => void,
): Promise<void> {
  const form = new FormData()
  if (payload.file) {
    form.append("file", payload.file)
  } else if (payload.jd_text) {
    form.append("jd_text", payload.jd_text)
  }
  if (payload.jd_url) {
    form.append("jd_url", payload.jd_url)
  }

  const res = await fetch(`${BASE}/api/fit/analyze`, {
    method: "POST",
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  })

  if (!res.ok) {
    const body = await res.json().catch(() => ({}))
    const detail = body?.detail
    const code = typeof detail === "object" ? detail?.code : detail
    const err = new Error(code ?? detail ?? `HTTP ${res.status}`) as Error & { code?: string }
    err.code = code
    throw err
  }

  if (!res.body) throw new Error("No response stream")

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ""
  let streamError: Error | null = null

  const consumeChunk = (chunk: string) => {
    for (const line of chunk.split("\n")) {
      if (!line.startsWith("data: ")) continue
      const parsed = JSON.parse(line.slice(6)) as import("./sse").SSEEvent
      onEvent(parsed)
      if (parsed.event === "error") {
        streamError = new Error(parsed.message ?? "Analysis failed.")
      }
    }
  }

  while (true) {
    const { done, value } = await reader.read()
    if (done) {
      if (buffer.trim()) consumeChunk(buffer)
      break
    }
    buffer += decoder.decode(value, { stream: true })
    const parts = buffer.split("\n\n")
    buffer = parts.pop() ?? ""
    for (const part of parts) consumeChunk(part)
    if (streamError) throw streamError
  }
  if (streamError) throw streamError
}

export async function getFitHistory(
  token: string,
  page = 1,
): Promise<FitHistoryResponse> {
  return request(`/api/fit/history?page=${page}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

export async function getFitDetail(
  token: string,
  analysisId: string,
): Promise<FitDetailResponse> {
  return request(`/api/fit/${analysisId}`, {
    headers: { Authorization: `Bearer ${token}` },
  })
}

// ── Billing types ─────────────────────────────────────────────────────────────

/** Per-period allowances from the backend tier-limits seed. null = no cap. */
export interface BillingPlanLimits {
  resumes_per_period: number;
  searches_per_period: number;
  fit_analyses_per_period: number;
  whisper_uses_per_period: number | null;
  career_watch_companies: number;
}

export interface BillingPlan {
  code: string;
  display_name: string;
  cycle: "daily" | "weekly" | "monthly" | "yearly";
  amount_cents: number;
  trial_days: number | null;
  stripe_price_id: string;
  is_active: boolean;
  features: string[];
  limits: BillingPlanLimits | null;
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

// ── Dashboard (Step 27/28) ───────────────────────────────────────────────────

export type ResumeRecordStatus =
  | "draft"
  | "applied"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export type ApplicationStatus = ResumeRecordStatus | "accepted";

export type ResumeSort = "date" | "ats_score" | "company";

export interface DashboardActivityItem {
  type: string;
  at: string;
  title: string;
  subtitle: string;
  meta: Record<string, unknown>;
}

export interface DashboardSummaryResponse {
  display_name: string;
  tier: string;
  credit_balance: number;
  spendable_credit_balance: number;
  credits_locked_until_verification: boolean;
  next_billing_date: string | null;
  subscription: {
    id: string;
    plan: string;
    billing_cycle: string;
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
  } | null;
  counts: {
    resumes: number;
    master_chunks: number;
    applications: number;
    saved_jobs: number;
  };
  recent_activity: DashboardActivityItem[];
  ats_trend: Array<{
    date: string;
    score: number;
    resume_id: string;
    jd_title: string;
    jd_company: string;
  }>;
}

export interface ResumeListItem {
  id: string;
  session_id: string;
  display_name: string | null;
  jd_title: string;
  jd_company: string;
  tags: string[];
  current_ats_score: number;
  starting_ats_score: number;
  ats_score_delta: number;
  status: ResumeRecordStatus;
  tailoring_stage: "in_progress" | "polished";
  created_at: string;
  updated_at: string;
}

export interface SessionResumeRecord {
  id: string;
  display_name: string | null;
  jd_title: string;
  jd_company: string;
  tailoring_stage: "in_progress" | "polished";
}

export async function getSessionResumeRecord(
  sessionId: string,
): Promise<SessionResumeRecord> {
  return request(`/api/sessions/${sessionId}/resume-record`);
}

export interface ResumeListResponse {
  items: ResumeListItem[];
  total: number;
  page: number;
  page_size: number;
}

export interface SubscriptionCurrentResponse {
  /** null when user has no subscription (free tier) */
  subscription: {
    id: string;
    /** Legacy interval enum (`daily` | `weekly` | `monthly`) — cannot identify the tier */
    plan: string;
    billing_cycle: "recurring" | "yearly";
    /** Canonical tier code, e.g. `monthly_plus` */
    plan_code: string;
    /** Marketing label, e.g. `Pro+` */
    plan_display_name: string;
    status: SubscriptionStatus;
    trial_ends_at: string | null;
    period_start: string;
    period_end: string;
    resumes_used: number;
    resumes_limit: number;
    searches_used: number;
    searches_limit: number;
    fit_analyses_limit: number;
    whisper_uses_used: number;
    /** null means unlimited (Premium fair-use) */
    whisper_uses_limit: number | null;
    cancel_at_period_end: boolean;
    paused_at: string | null;
    pause_resumes_at: string | null;
  } | null;
  /** Free credit balance (relevant when subscription is null) */
  credit_balance: number;
  spendable_credit_balance: number;
  credits_locked_until_verification: boolean;
}

// ── Resume Chat ──────────────────────────────────────────────────────────────

export interface ResumePatch {
  section: "summary" | "experience" | "skills" | "education" | "certifications" | "projects" | "contact";
  description: string;
  // Contact
  new_name?: string;
  // Summary
  new_summary?: string;
  // Skills
  add_skills?: string[];
  remove_skills?: string[];
  // Experience
  company?: string;
  bullet_old?: string;
  bullet_new?: string;
  title_old?: string;
  new_title?: string;
  dates_old?: string;
  new_dates?: string;
  delete_experience?: boolean;
  // Certifications
  remove_certifications?: string[];
  add_certifications?: string[];
  // Education
  institution?: string;
  institution_old?: string;
  new_institution?: string;
  new_degree?: string;
  add_education_bullets?: string[];
  education_bullet_old?: string;
  education_bullet_new?: string;
  // Projects
  remove_projects?: string[];
  project_name?: string;
  project_bullet_old?: string;
  project_bullet_new?: string;
  project_bullets_replace_all?: string[];
  new_project_title?: string;
  new_project_description?: string;
  new_project?: { name: string; description?: string; bullets: string[] } | null;
}

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface ChatResponse {
  reply: string;
  patches: ResumePatch[];
}

/** Overwrite the full tailored resume (used by chat agent after applying a patch). */
export async function saveTailoredResume(
  sessionId: string,
  tailored: TailoredResumeOutput,
): Promise<{ ok: boolean }> {
  return request(`/api/sessions/${sessionId}/tailored`, {
    method: "PATCH",
    body: JSON.stringify({ tailored_output: tailored }),
  });
}

/** Save polished resume and sync master profile + RAG vectors (name, dates, titles). */
export async function commitTailoredResume(
  sessionId: string,
  tailored: TailoredResumeOutput,
): Promise<{ ok: boolean }> {
  return request(`/api/sessions/${sessionId}/tailored/commit`, {
    method: "POST",
    body: JSON.stringify({ tailored_output: tailored }),
  });
}

export async function chatWithResume(
  sessionId: string,
  payload: {
    message: string;
    history: ChatMessage[];
    tailored_snapshot?: TailoredResumeOutput;
  },
): Promise<ChatResponse> {
  return request(`/api/sessions/${sessionId}/chat`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
