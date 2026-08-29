/** Backend admin session-gone codes surfaced to the auth page. */
export const ADMIN_SESSION_GONE_CODES = new Set([
  "admin_session_revoked",
  "admin_session_expired",
  "admin_session_idle",
  "admin_session_binding_mismatch",
  "admin_token_invalid",
  "admin_unauthenticated",
  "admin_not_found",
])

/** Map backend ``detail.code`` to ``/admin/auth?reason=`` query values. */
export function mapAdminSessionGoneCodeToReason(code: string): string {
  switch (code) {
    case "admin_session_idle":
      return "idle"
    case "admin_session_expired":
      return "expired"
    case "admin_session_revoked":
      return "session_revoked"
    case "admin_session_binding_mismatch":
      return "binding_mismatch"
    default:
      return "session_revoked"
  }
}

/** Build redirect target used by the admin layout on session-gone events. */
export function adminAuthRedirectPathForSessionCode(code: string): string {
  return `/admin/auth?reason=${mapAdminSessionGoneCodeToReason(code)}`
}

/** User-facing copy for each ``?reason=`` on /admin/auth. */
export function adminAuthReasonMessage(reason: string | null): string | null {
  switch (reason) {
    case "expired":
      return "Your admin session reached its 60-minute limit. Please sign in again."
    case "idle":
      return "Your admin session timed out after 15 minutes of inactivity. Please sign in again."
    case "session_revoked":
      return "You signed in from another browser or device. This session is no longer valid."
    case "binding_mismatch":
      return "Your session could not be verified (network or browser changed). Please sign in again."
    case "setup_password":
      return "First login: choose a new password before accessing the admin panel."
    default:
      return null
  }
}
