/**
 * BYOK key store — persists to sessionStorage only.
 * Keys are never sent to any server except as request headers for the
 * user's own LLM calls. They vanish when the browser tab closes.
 */

const STORE_KEY = "sr_byok";

export interface KeyEntry {
  provider: string;
  model: string;
  apiKey: string; // masked after first save
}

function load(): KeyEntry | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = sessionStorage.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as KeyEntry) : null;
  } catch {
    return null;
  }
}

function save(entry: KeyEntry): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(STORE_KEY, JSON.stringify(entry));
}

function clear(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(STORE_KEY);
}

/** Returns the stored key entry, or null if nothing is saved. */
export function getStoredKey(): KeyEntry | null {
  return load();
}

/** Persists the user's key for this browser session. */
export function storeKey(entry: KeyEntry): void {
  save(entry);
}

/** Removes the stored key. */
export function clearKey(): void {
  clear();
}

/** Returns HTTP headers to attach to every API request. */
export function byokHeaders(): Record<string, string> {
  const entry = load();
  if (!entry?.apiKey) return {};
  const headers: Record<string, string> = {
    "X-Api-Key": entry.apiKey,
    "X-Provider": entry.provider,
    "X-Model": entry.model,
  };
  return headers;
}
