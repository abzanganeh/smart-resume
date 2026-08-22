const STORAGE_KEY = "sr_signup_device_fp_v1"

/** Stable browser-local ID for signup rate-limit pairing (hashed server-side). */
export function getSignupDeviceFingerprint(): string {
  if (typeof window === "undefined") return ""

  try {
    const existing = window.localStorage.getItem(STORAGE_KEY)
    if (existing && existing.length >= 16) return existing

    const created = crypto.randomUUID()
    window.localStorage.setItem(STORAGE_KEY, created)
    return created
  } catch {
    return crypto.randomUUID()
  }
}
