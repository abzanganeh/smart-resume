/**
 * Platform AI mode — legacy BYOK localStorage keys are cleared on load.
 */

const LEGACY_STORE_KEY = "sr_byok";
const LEGACY_AI_MODE_KEY = "sr_ai_mode";
export const BYOK_CHANGE_EVENT = "sr_byok_changed";

export type AiMode = "platform";

export interface KeyEntry {
  provider: string;
  model: string;
  apiKey: string;
}

function clearLegacyByokStorage(): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.removeItem(LEGACY_STORE_KEY);
    window.localStorage.removeItem(LEGACY_AI_MODE_KEY);
    window.sessionStorage.removeItem(LEGACY_STORE_KEY);
    window.sessionStorage.removeItem(LEGACY_AI_MODE_KEY);
  } catch {
    // ignore quota / private mode errors
  }
}

clearLegacyByokStorage();

/** Returns null — user API keys are no longer supported. */
export function getStoredKey(): KeyEntry | null {
  return null;
}

/** Always platform mode. */
export function getAiMode(): AiMode {
  return "platform";
}

export function setAiMode(_mode: AiMode): void {
  notifyChange();
}

/** Subscribe to AI mode changes in this tab (no-op for platform-only). */
export function subscribeByokChanges(listener: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  window.addEventListener(BYOK_CHANGE_EVENT, listener);
  return () => window.removeEventListener(BYOK_CHANGE_EVENT, listener);
}

/** No-op — keys are not stored client-side. */
export function storeKey(_entry: KeyEntry): void {
  notifyChange();
}

/** No-op. */
export function clearKey(): void {
  notifyChange();
}

function notifyChange(): void {
  if (typeof window === "undefined") return;
  window.dispatchEvent(new CustomEvent(BYOK_CHANGE_EVENT));
}

/** Platform AI only — no BYOK headers attached to API requests. */
export function byokHeaders(): Record<string, string> {
  return {};
}
