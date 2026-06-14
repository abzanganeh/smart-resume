/** Extension-captured job descriptions (Strategy B Phase 2). */

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export interface ExtensionJobDescription {
  id: string;
  url: string | null;
  title: string | null;
  company: string | null;
  text: string;
  source: string;
  created_at: string;
}

export async function getExtensionJobDescription(
  token: string,
  jdId: string,
): Promise<ExtensionJobDescription> {
  const res = await fetch(`${BASE}/api/job-descriptions/${encodeURIComponent(jdId)}`, {
    headers: { Authorization: `Bearer ${token}` },
  });
  if (!res.ok) {
    throw new Error(`Could not load saved job (${res.status})`);
  }
  return res.json() as Promise<ExtensionJobDescription>;
}
