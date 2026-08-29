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

const RESOLVED_ORIGIN = resolveSiteOrigin(
  process.env.NEXT_PUBLIC_SITE_URL ?? process.env.NEXTAUTH_URL,
);

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

/** True when the public site is plain HTTP on loopback (local Docker staging on :3001). */
export function isLocalHttpSite(): boolean {
  return isLocalHttpOrigin(RESOLVED_ORIGIN);
}

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path: string): string {
  return new URL(path, siteUrl()).toString();
}
