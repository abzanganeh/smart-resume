const RETURN_URL_KEY = "sr_auth_return_url"

/** Remember where to return after sign-in (survives OAuth round-trips). */
export function saveAuthReturnUrl(path?: string): void {
  if (typeof window === "undefined") return
  const target = path ?? `${window.location.pathname}${window.location.search}`
  if (!target || target.startsWith("/auth")) return
  sessionStorage.setItem(RETURN_URL_KEY, target)
}

/** Prefer explicit callbackUrl, then stored return path, then fallback. */
export function resolveAuthReturnUrl(
  callbackUrlFromQuery: string | null | undefined,
  fallback = "/dashboard",
): string {
  if (callbackUrlFromQuery && callbackUrlFromQuery !== "/auth") {
    return callbackUrlFromQuery
  }
  if (typeof window === "undefined") return fallback
  const stored = sessionStorage.getItem(RETURN_URL_KEY)
  if (stored && !stored.startsWith("/auth")) {
    sessionStorage.removeItem(RETURN_URL_KEY)
    return stored
  }
  return fallback
}
