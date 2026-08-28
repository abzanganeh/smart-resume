const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PolishResumeResponse {
  text: string;
}

export async function polishResume(
  text: string,
  instruction: string,
  token: string,
): Promise<PolishResumeResponse> {
  const res = await fetch(`${BASE}/api/profile/resume/polish`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ text, instruction }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string } | string };
    const msg = typeof body.detail === "object"
      ? (body.detail?.message ?? "Polish request failed")
      : (body.detail ?? "Polish request failed");
    throw new Error(msg);
  }

  return res.json() as Promise<PolishResumeResponse>;
}

export type VerifyStatus = "ok" | "review";

export interface VerifyItem {
  field: string;
  spoken: string;
  resume: string;
  status: VerifyStatus;
  message: string;
}

export interface StoryBillingInfo {
  charged_to: string;
  action: string;
}

export interface StoryPreviewResponse {
  resume_text: string;
  verify_items: VerifyItem[];
  verify_review_count: number;
  billing: StoryBillingInfo;
}

export interface StorySaveResponse {
  id: string;
  chunk_count: number;
  last_embedded_at: string | null;
  resume_text: string;
  embedding_warning: string | null;
  billing: StoryBillingInfo;
}

function parseApiError(body: unknown, fallback: string): string {
  const detail = (body as { detail?: { message?: string } | string })?.detail;
  if (typeof detail === "object" && detail?.message) return detail.message;
  if (typeof detail === "string") return detail;
  return fallback;
}

export async function generateStoryPreview(
  segments: string[],
  token: string,
  options: { whisperPath?: boolean; storySessionId?: string } = {},
): Promise<StoryPreviewResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.storySessionId) {
    headers["X-Story-Session-Id"] = options.storySessionId;
  }

  const res = await fetch(`${BASE}/api/profile/resume/from-story`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      segments,
      whisper_path: options.whisperPath ?? false,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(parseApiError(body, "Story conversion failed"));
  }

  return res.json() as Promise<StoryPreviewResponse>;
}

/** Alias for generateStoryPreview */
export const submitStory = generateStoryPreview;

export async function refreshStoryVerify(
  segments: string[],
  resumeText: string,
  token: string,
): Promise<{ verify_items: VerifyItem[]; verify_review_count: number }> {
  const res = await fetch(`${BASE}/api/profile/resume/story-verify`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({ segments, resume_text: resumeText }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(parseApiError(body, "Verify refresh failed"));
  }

  return res.json() as Promise<{ verify_items: VerifyItem[]; verify_review_count: number }>;
}

export async function saveStoryResume(
  resumeText: string,
  token: string,
  options: {
    segments?: string[];
    whisperPath?: boolean;
    storySessionId?: string;
    attestationConfirmed: boolean;
  },
): Promise<StorySaveResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.storySessionId) {
    headers["X-Story-Session-Id"] = options.storySessionId;
  }

  const res = await fetch(`${BASE}/api/profile/resume/from-story/save`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      resume_text: resumeText,
      segments: options.segments ?? [],
      attestation_confirmed: options.attestationConfirmed,
      whisper_path: options.whisperPath ?? false,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(parseApiError(body, "Save to profile failed"));
  }

  return res.json() as Promise<StorySaveResponse>;
}

export function storyGenerateCreditLabel(chargedTo: string | undefined, isFreeUser: boolean): string {
  if (!isFreeUser) return "Included in your plan";
  if (chargedTo === "first_story_generate") return "First generate free";
  if (chargedTo === "subscription") return "Included in your plan";
  return "1 credit";
}

export function storySaveCreditLabel(chargedTo: string | undefined, isFreeUser: boolean): string {
  if (!isFreeUser) return "Included in your plan";
  if (chargedTo === "first_story_save") return "First save free";
  if (chargedTo === "subscription") return "Included in your plan";
  return "1 credit";
}

// ---------------------------------------------------------------------------
// Story Mode Interview Coach (§22)
// ---------------------------------------------------------------------------

export interface CoachMessage {
  role: "coach" | "user";
  text: string;
}

export interface CoachDelta {
  delta?: string;
  done?: boolean;
  complete?: boolean;
  error?: string;
}

/** Parse one SSE `data:` payload; throws on server error events. */
function consumeSseDataLine(
  raw: string,
  onDelta: (delta: string) => void,
  label: "Coach" | "Interview",
): { done: boolean; complete: boolean } {
  let evt: CoachDelta;
  try {
    evt = JSON.parse(raw) as CoachDelta;
  } catch {
    return { done: false, complete: false };
  }
  if (evt.error) {
    const err = new Error(
      evt.error === "free_tier_ai_cap_reached"
        ? "You've used up the free-plan AI allowance. Upgrade to keep using the coach."
        : label === "Coach"
          ? "The coach could not respond. Please retry in a moment."
          : "The interview could not start. Please retry in a moment.",
    ) as Error & { code?: string };
    err.code = evt.error;
    throw err;
  }
  if (evt.delta) onDelta(evt.delta);
  if (evt.done) {
    return { done: true, complete: evt.complete ?? false };
  }
  return { done: false, complete: false };
}

async function readSseStream(
  reader: ReadableStreamDefaultReader<Uint8Array>,
  onDelta: (delta: string) => void,
  label: "Coach" | "Interview",
): Promise<{ complete: boolean }> {
  const decoder = new TextDecoder();
  let buffer = "";
  let isComplete = false;

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const raw = line.slice(6).trim();
      if (!raw) continue;
      const result = consumeSseDataLine(raw, onDelta, label);
      if (result.done) isComplete = result.complete;
    }
  }

  return { complete: isComplete };
}

export async function streamCoach(
  segmentText: string,
  history: CoachMessage[],
  token: string,
  onDelta: (delta: string) => void,
  options: { sessionId?: string } = {},
): Promise<{ complete: boolean }> {
  const res = await fetch(`${BASE}/api/profile/story/coach`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      segment_text: segmentText,
      history,
      session_id: options.sessionId ?? null,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string; code?: string } | string };
    const detail = body.detail;
    const msg = typeof detail === "object"
      ? (detail?.message ?? "Coaching request failed")
      : (detail ?? "Coaching request failed");
    const code = typeof detail === "object" ? detail?.code : undefined;
    const err = new Error(msg) as Error & { code?: string };
    err.code = code;
    throw err;
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body from coach endpoint");

  return readSseStream(reader, onDelta, "Coach");
}

// ---------------------------------------------------------------------------
// Coached Interview Mode (§23)
// ---------------------------------------------------------------------------

export interface InterviewMessage {
  role: "interviewer" | "user";
  text: string;
}

export async function streamInterviewQuestion(
  history: InterviewMessage[],
  token: string,
  onDelta: (delta: string) => void,
  options: { sessionId?: string } = {},
): Promise<{ complete: boolean }> {
  const res = await fetch(`${BASE}/api/profile/story/interview/next`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      history,
      session_id: options.sessionId ?? null,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string; code?: string } | string };
    const detail = body.detail;
    const msg = typeof detail === "object"
      ? (detail?.message ?? "Interview request failed")
      : (detail ?? "Interview request failed");
    const code = typeof detail === "object" ? detail?.code : undefined;
    const err = new Error(msg) as Error & { code?: string };
    err.code = code;
    throw err;
  }

  const reader = res.body?.getReader();
  if (!reader) throw new Error("No response body from interview endpoint");

  return readSseStream(reader, onDelta, "Interview");
}

export async function submitInterview(
  history: InterviewMessage[],
  token: string,
  options: { whisperPath?: boolean } = {},
): Promise<StoryPreviewResponse> {
  const res = await fetch(`${BASE}/api/profile/story/interview/submit`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      history,
      whisper_path: options.whisperPath ?? false,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string } | string };
    const msg = typeof body.detail === "object"
      ? (body.detail?.message ?? "Interview submission failed")
      : (body.detail ?? "Interview submission failed");
    throw new Error(msg);
  }

  return res.json() as Promise<StoryPreviewResponse>;
}
