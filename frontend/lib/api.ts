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

export async function triggerPhase(
  sessionId: string,
  phase: number
): Promise<{ job_id: string; stream_url: string }> {
  return request(`/api/sessions/${sessionId}/phases/${phase}/run`, {
    method: "POST",
  });
}

export function phaseEventsUrl(sessionId: string, phase: number): string {
  return `${BASE}/api/sessions/${sessionId}/phases/${phase}/events`;
}

// ── Tailored resume edits ────────────────────────────────────────────────────

export async function patchTailoredResume(
  sessionId: string,
  patch: Record<string, unknown>
): Promise<{ version: number; snapshot_id: string }> {
  return request<{ version: number; snapshot_id: string }>(
    `/api/sessions/${sessionId}/resume/tailored`,
    { method: "PATCH", body: JSON.stringify(patch) }
  );
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

// ── Export ───────────────────────────────────────────────────────────────────

export function exportUrl(
  sessionId: string,
  format: "pdf" | "docx" | "txt"
): string {
  return `${BASE}/api/sessions/${sessionId}/export?format=${format}`;
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface UserInfoPayload {
  name: string;
  email: string;
  phone?: string;
  linkedin?: string;
  github?: string;
  career_stage: "early_mid" | "senior";
  target_role_type: "ml_engineer" | "swe" | "data_scientist" | "other";
  certifications: string[];
  is_transitioning_to_ml: boolean;
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

export interface TailoredResumeOutput {
  contact: Record<string, string>;
  summary: string;
  skills: string[];
  experience: TailoredExperience[];
  projects: Record<string, unknown>[];
  education: Record<string, unknown>[];
  certifications: string[];
  rewrite_notes: string[];
  metrics_needed: MetricNeeded[];
}

export interface QAItem {
  item: string;
  status: "pass" | "warn" | "fail";
  note: string;
}

export interface QAOutput {
  checklist: QAItem[];
  overall_status: "pass" | "warn" | "fail";
  user_action_required: string[];
}
