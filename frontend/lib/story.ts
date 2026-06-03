const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface PolishResumeResponse {
  text: string;
}

export async function polishResume(
  text: string,
  instruction: string,
  token: string,
  options: { byokApiKey?: string; byokProvider?: string; byokModel?: string } = {},
): Promise<PolishResumeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.byokApiKey)   headers["X-Api-Key"]  = options.byokApiKey;
  if (options.byokProvider) headers["X-Provider"] = options.byokProvider;
  if (options.byokModel)    headers["X-Model"]    = options.byokModel;

  const res = await fetch(`${BASE}/api/profile/resume/polish`, {
    method: "POST",
    headers,
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
  options: {
    byokApiKey?: string;
    byokProvider?: string;
    byokModel?: string;
    whisperPath?: boolean;
  } = {},
): Promise<StoryToResumeResponse> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.byokApiKey)   headers["X-Api-Key"]   = options.byokApiKey;
  if (options.byokProvider) headers["X-Provider"]  = options.byokProvider;
  if (options.byokModel)    headers["X-Model"]     = options.byokModel;

  const res = await fetch(`${BASE}/api/profile/resume/from-story`, {
    method: "POST",
    headers,
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

/**
 * Stream one coaching question from the backend.
 *
 * Yields string deltas; resolves with { complete: boolean } on completion.
 *
 * @param segmentText   Transcript of the segment being coached
 * @param history       Prior coach/user exchanges in this session
 * @param token         Auth JWT
 * @param onDelta       Called with each streamed text fragment
 * @param options       BYOK / model overrides
 */
export async function streamCoach(
  segmentText: string,
  history: CoachMessage[],
  token: string,
  onDelta: (delta: string) => void,
  options: {
    byokApiKey?: string;
    byokProvider?: string;
    byokModel?: string;
    sessionId?: string;
  } = {},
): Promise<{ complete: boolean }> {
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (options.byokApiKey)   headers["X-Api-Key"]  = options.byokApiKey;
  if (options.byokProvider) headers["X-Provider"] = options.byokProvider;
  if (options.byokModel)    headers["X-Model"]    = options.byokModel;

  const res = await fetch(`${BASE}/api/profile/story/coach`, {
    method: "POST",
    headers,
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
      try {
        const evt = JSON.parse(raw) as CoachDelta;
        if (evt.error) throw new Error(`Coach error: ${evt.error}`);
        if (evt.delta) onDelta(evt.delta);
        if (evt.done) {
          isComplete = evt.complete ?? false;
        }
      } catch {
        // malformed SSE line — skip
      }
    }
  }

  return { complete: isComplete };
}
