/** Backend auth failures that mean the browser session should be cleared. */
export const STALE_AUTH_MESSAGES = new Set([
  "User not found",
  "Invalid access token",
  "Access token expired",
  "missing_refresh_token",
  "refresh_token_invalid",
  "refresh_token_expired",
  "refresh_token_reuse",
])

export function isStaleAuthError(message: string): boolean {
  return STALE_AUTH_MESSAGES.has(message)
}
