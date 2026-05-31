const STORAGE_KEY = "sr_recent_sessions";
const MAX_RECENT = 12;

export interface RecentSessionEntry {
  session_id: string;
  label: string;
  updated_at: string;
}

function load(): RecentSessionEntry[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? (JSON.parse(raw) as RecentSessionEntry[]) : [];
  } catch {
    return [];
  }
}

function save(entries: RecentSessionEntry[]): void {
  if (typeof window === "undefined") return;
  localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(0, MAX_RECENT)));
}

/** Track a session the user opened or created (for cover-letter picker). */
export function trackRecentSession(sessionId: string, label?: string): void {
  const now = new Date().toISOString();
  const existing = load().filter((e) => e.session_id !== sessionId);
  const entry: RecentSessionEntry = {
    session_id: sessionId,
    label: label ?? `Session ${sessionId.slice(0, 8)}…`,
    updated_at: now,
  };
  save([entry, ...existing]);
}

export function getRecentSessions(): RecentSessionEntry[] {
  return load();
}
