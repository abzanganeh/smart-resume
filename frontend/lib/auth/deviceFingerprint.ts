const STORAGE_KEY = "sr_signup_device_fp_v1"
export const SIGNUP_DEVICE_FP_COOKIE = "sr_signup_device_fp"

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

/** Persist fingerprint in a short-lived cookie for the OAuth return hop. */
export function persistSignupDeviceFingerprintForOAuth(): void {
  if (typeof window === "undefined") return
  const fp = getSignupDeviceFingerprint()
  if (fp.length < 16) return
  document.cookie = `${SIGNUP_DEVICE_FP_COOKIE}=${encodeURIComponent(fp)}; path=/; max-age=600; samesite=lax`
}
