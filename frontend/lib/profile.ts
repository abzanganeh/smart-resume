/**
 * Master resume profile API helpers and pure utilities for /profile.
 */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"

function authHeaders(token: string, extra?: HeadersInit): HeadersInit {
  return {
    Authorization: `Bearer ${token}`,
    ...(extra ?? {}),
  }
}

async function parseError(res: Response): Promise<string> {
  try {
    const body = await res.json()
    return body?.detail ?? `HTTP ${res.status}`
  } catch {
    return `HTTP ${res.status}`
  }
}

// ── Types ────────────────────────────────────────────────────────────────────

export interface ProfileChunk {
  id: string
  section_type: string
  content: string
  token_count: number
  metadata: Record<string, unknown>
  created_at: string | null
  updated_at: string | null
  deleted_at?: string | null
  score?: number | null
}

export interface ProfileResume {
  id: string | null
  raw_text: string
  parsed_sections: Record<string, unknown>
  chunk_count: number
  last_embedded_at: string | null
  created_at: string | null
  updated_at: string | null
}

export interface ProfileUploadResponse extends ProfileResume {
  chunks: ProfileChunk[]
}

// ── Section display ──────────────────────────────────────────────────────────

export const SECTION_ORDER = [
  "summary",
  "experience",
  "skills",
  "education",
  "project",
  "cert",
  "publication",
  "award",
  "volunteer",
  "language",
  "patent",
  "other",
] as const

export const SECTION_LABELS: Record<string, string> = {
  summary: "Summary",
  experience: "Experience",
  skills: "Skills",
  education: "Education",
  project: "Projects",
  cert: "Certifications",
  publication: "Publications",
  award: "Awards",
  volunteer: "Volunteer",
  language: "Languages",
  patent: "Patents",
  other: "Other",
}

// ── Pure helpers (unit-tested) ───────────────────────────────────────────────

/** Rough cl100k_base estimate (~4 chars per token for English prose). */
export function estimateTokenCount(text: string): number {
  const trimmed = text.trim()
  if (!trimmed) return 0
  return Math.max(1, Math.ceil(trimmed.length / 4))
}

/** Embedding cost at $0.0000001 per token; always shown as "< $0.001" when tiny. */
export function formatEmbeddingCost(tokenCount: number): string {
  const usd = tokenCount * 0.0000001
  if (usd < 0.001) return "< $0.001"
  return `$${usd.toFixed(4)}`
}

export function groupChunksBySection(
  chunks: ProfileChunk[],
): Map<string, ProfileChunk[]> {
  const grouped = new Map<string, ProfileChunk[]>()
  for (const chunk of chunks) {
    const key = chunk.section_type || "other"
    const list = grouped.get(key) ?? []
    list.push(chunk)
    grouped.set(key, list)
  }
  return grouped
}

export function liveChunkCount(chunks: ProfileChunk[]): number {
  return chunks.filter((c) => !c.deleted_at).length
}

export function buildPatchChunkUrl(chunkId: string): string {
  return `${BASE}/api/profile/resume/chunks/${chunkId}`
}

// ── API calls ────────────────────────────────────────────────────────────────

export async function getProfileResume(token: string): Promise<ProfileResume> {
  const res = await fetch(`${BASE}/api/profile/resume`, {
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function getProfileChunks(token: string): Promise<ProfileChunk[]> {
  const res = await fetch(`${BASE}/api/profile/resume/chunks`, {
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(await parseError(res))
  const body = (await res.json()) as { chunks: ProfileChunk[] }
  return body.chunks
}

export async function uploadProfileResume(
  token: string,
  payload: { file?: File; text?: string },
): Promise<ProfileUploadResponse> {
  const form = new FormData()
  if (payload.file) {
    form.append("file", payload.file)
  } else if (payload.text) {
    form.append("text", payload.text)
  }

  const res = await fetch(`${BASE}/api/profile/resume`, {
    method: "POST",
    headers: authHeaders(token),
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function reembedAllProfileResume(
  token: string,
  rawText: string,
): Promise<ProfileUploadResponse> {
  const form = new FormData()
  form.append("text", rawText)

  const res = await fetch(`${BASE}/api/profile/resume`, {
    method: "PUT",
    headers: authHeaders(token),
    body: form,
  })
  if (!res.ok) throw new Error(await parseError(res))
  return res.json()
}

export async function patchProfileChunk(
  token: string,
  chunkId: string,
  content: string,
): Promise<ProfileChunk> {
  const res = await fetch(buildPatchChunkUrl(chunkId), {
    method: "PATCH",
    headers: authHeaders(token, { "Content-Type": "application/json" }),
    body: JSON.stringify({ content }),
  })
  if (!res.ok) throw new Error(await parseError(res))
  const body = (await res.json()) as { chunk: ProfileChunk }
  return body.chunk
}

export async function deleteProfileChunk(
  token: string,
  chunkId: string,
): Promise<void> {
  const res = await fetch(`${BASE}/api/profile/resume/chunks/${chunkId}`, {
    method: "DELETE",
    headers: authHeaders(token),
  })
  if (!res.ok) throw new Error(await parseError(res))
}

/** Placeholder until GET /api/resumes?has_master_resume=true ships (Step 27). */
export async function fetchTailoredResumeCount(token: string): Promise<number | null> {
  try {
    const res = await fetch(
      `${BASE}/api/resumes?has_master_resume=true`,
      { headers: authHeaders(token) },
    )
    if (!res.ok) return null
    const body = (await res.json()) as { total?: number; resumes?: unknown[] }
    if (typeof body.total === "number") return body.total
    if (Array.isArray(body.resumes)) return body.resumes.length
    return null
  } catch {
    return null
  }
}
