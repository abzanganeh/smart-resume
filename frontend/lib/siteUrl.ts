/**
 * Canonical public origin, for `metadataBase`, the sitemap, and robots.txt.
 *
 * `NEXT_PUBLIC_SITE_URL` is the explicit override and is inlined at **build**
 * time when set — which is what makes sitemap/robots URLs correct in Docker
 * images. `NEXTAUTH_URL` is read once at module load as a dev/CI fallback;
 * `auth.ts` may delete it later for local OAuth, so we must not read env on
 * every call.
 */

const FALLBACK_ORIGIN = "http://localhost:3000";

/** Pure resolver — test this rather than mutating `process.env` at call time. */
export function resolveSiteOrigin(raw: string | undefined): string {
  if (!raw) return FALLBACK_ORIGIN;

  try {
    return new URL(raw).origin;
  } catch {
    return FALLBACK_ORIGIN;
  }
}

const RAW_SITE_ENV = process.env.NEXT_PUBLIC_SITE_URL ?? process.env.NEXTAUTH_URL;

const RESOLVED_ORIGIN = resolveSiteOrigin(RAW_SITE_ENV);

export function siteUrl(): string {
  return RESOLVED_ORIGIN;
}

/** True when ``origin`` is plain HTTP on loopback (local Docker staging on :3001). */
export function isLocalHttpOrigin(origin: string): boolean {
  try {
    const u = new URL(origin);
    return (
      u.protocol === "http:" &&
      (u.hostname === "localhost" || u.hostname === "127.0.0.1")
    );
  } catch {
    return false;
  }
}

/**
 * Whether CSP/HSTS should treat the deployment as local HTTP staging.
 * Unset site env fails closed (production headers) even though ``siteUrl()``
 * still falls back to localhost for metadata links.
 */
export function isExplicitLocalHttpSite(
  rawSiteEnv: string | undefined,
  resolvedOrigin: string = resolveSiteOrigin(rawSiteEnv),
): boolean {
  if (!rawSiteEnv?.trim()) return false;
  return isLocalHttpOrigin(resolvedOrigin);
}

/** True when the public site is plain HTTP on loopback (local Docker staging on :3001). */
export function isLocalHttpSite(): boolean {
  return isExplicitLocalHttpSite(RAW_SITE_ENV, RESOLVED_ORIGIN);
}

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path: string): string {
  return new URL(path, siteUrl()).toString();
}
