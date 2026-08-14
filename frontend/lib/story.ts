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

export interface StoryToResumeResponse {
  id: string;
  chunk_count: number;
  last_embedded_at: string | null;
  resume_text: string | null;
  embedding_warning: string | null;
}

export async function submitStory(
  segments: string[],
  token: string,
  options: { whisperPath?: boolean } = {},
): Promise<StoryToResumeResponse> {
  const res = await fetch(`${BASE}/api/profile/resume/from-story`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    },
    body: JSON.stringify({
      segments,
      whisper_path: options.whisperPath ?? false,
    }),
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({})) as { detail?: { message?: string } | string };
    const msg = typeof body.detail === "object"
      ? (body.detail?.message ?? "Story conversion failed")
      : (body.detail ?? "Story conversion failed");
    throw new Error(msg);
  }

  return res.json() as Promise<StoryToResumeResponse>;
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
    throw new Error(
      label === "Coach"
        ? "The coach could not respond. Please retry in a moment."
        : "The interview could not start. Please retry in a moment.",
    );
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
): Promise<StoryToResumeResponse> {
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

  return res.json() as Promise<StoryToResumeResponse>;
}
