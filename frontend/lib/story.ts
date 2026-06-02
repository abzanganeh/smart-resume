const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface StoryToResumeResponse {
  id: string;
  chunk_count: number;
  last_embedded_at: string | null;
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
