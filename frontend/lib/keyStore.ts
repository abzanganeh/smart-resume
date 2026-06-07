/**
 * BYOK key store — persists to sessionStorage only.
 * Keys are never sent to any server except as request headers for the
 * user's own LLM calls. They vanish when the browser tab closes.
 */

const STORE_KEY = "sr_byok";
const AI_MODE_KEY = "sr_ai_mode";
export const BYOK_CHANGE_EVENT = "sr_byok_changed";

export type AiMode = "platform" | "byok";

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

function notifyChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(BYOK_CHANGE_EVENT));
}

/** Platform AI uses Smart Resume credits; BYOK sends the user's key. */
export function getAiMode(): AiMode {
  if (typeof window === "undefined") return "platform";
  const explicit = sessionStorage.getItem(AI_MODE_KEY);
  if (explicit === "platform" || explicit === "byok") return explicit;
  const entry = load();
  if (entry?.apiKey && entry.apiKey !== "__env__") return "byok";
  return "platform";
}

export function setAiMode(mode: AiMode): void {
  if (typeof window === "undefined") return;
  sessionStorage.setItem(AI_MODE_KEY, mode);
  notifyChange();
}

/** Subscribe to BYOK / AI mode changes in this tab. */
export function subscribeByokChanges(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(BYOK_CHANGE_EVENT, listener);
  return () => window.removeEventListener(BYOK_CHANGE_EVENT, listener);
}

/** Persists the user's key for this browser session. */
export function storeKey(entry: KeyEntry): void {
  save(entry);
  setAiMode("byok");
  notifyChange();
}

/** Removes the stored key. */
export function clearKey(): void {
  clear();
  notifyChange();
}

/** Returns HTTP headers to attach to every API request. */
export function byokHeaders(): Record<string, string> {
  if (getAiMode() === "platform") {
    return { "X-Use-Platform": "true" };
  }
  const entry = load();
  if (!entry?.apiKey || entry.apiKey === "__env__") return {};
  return {
    "X-Api-Key": entry.apiKey,
    "X-Provider": entry.provider,
    "X-Model": entry.model,
  };
}
