/**
 * BYOK key store — persists to localStorage on this device only.
 * Keys are never sent to Smart Resume servers for storage; they are attached
 * as request headers for your own LLM calls only.
 */

const STORE_KEY = "sr_byok";
const AI_MODE_KEY = "sr_ai_mode";
export const BYOK_CHANGE_EVENT = "sr_byok_changed";

export type AiMode = "platform" | "byok";

export interface KeyEntry {
  provider: string;
  model: string;
  apiKey: string;
}

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  return window.localStorage;
}

function migrateLegacySessionStorage(): void {
  if (typeof window === "undefined") return;
  const store = storage();
  if (!store || store.getItem(STORE_KEY)) return;
  try {
    const legacy = window.sessionStorage.getItem(STORE_KEY);
    if (legacy) {
      store.setItem(STORE_KEY, legacy);
      window.sessionStorage.removeItem(STORE_KEY);
    }
    const legacyMode = window.sessionStorage.getItem(AI_MODE_KEY);
    if (legacyMode && !store.getItem(AI_MODE_KEY)) {
      store.setItem(AI_MODE_KEY, legacyMode);
      window.sessionStorage.removeItem(AI_MODE_KEY);
    }
  } catch {
    // ignore quota / private mode errors
  }
}

function load(): KeyEntry | null {
  migrateLegacySessionStorage();
  const store = storage();
  if (!store) return null;
  try {
    const raw = store.getItem(STORE_KEY);
    return raw ? (JSON.parse(raw) as KeyEntry) : null;
  } catch {
    return null;
  }
}

function save(entry: KeyEntry): void {
  storage()?.setItem(STORE_KEY, JSON.stringify(entry));
}

function clear(): void {
  storage()?.removeItem(STORE_KEY);
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
  const explicit = window.localStorage.getItem(AI_MODE_KEY);
  if (explicit === "platform" || explicit === "byok") return explicit;
  const entry = load();
  if (entry?.apiKey && entry.apiKey !== "__env__") return "byok";
  return "platform";
}

export function setAiMode(mode: AiMode): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(AI_MODE_KEY, mode);
  notifyChange();
}

/** Subscribe to BYOK / AI mode changes in this tab. */
export function subscribeByokChanges(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(BYOK_CHANGE_EVENT, listener);
  return () => window.removeEventListener(BYOK_CHANGE_EVENT, listener);
}

/** Persists the user's key on this browser/device (localStorage). */
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
