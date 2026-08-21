/**
 * Canonical public origin, for `metadataBase`, the sitemap, and robots.txt.
 *
 * Resolution order is explicit override, then the NextAuth origin (which every
 * environment already sets, including Playwright and both compose files), then
 * localhost. A malformed value falls back rather than throwing: this is called
 * during module evaluation of the root layout, so a bad env var would otherwise
 * take down every route instead of degrading one meta tag.
 */

const FALLBACK_ORIGIN = "http://localhost:3000";

export function siteUrl(): string {
  const raw =
    process.env.NEXT_PUBLIC_SITE_URL ?? process.env.NEXTAUTH_URL ?? FALLBACK_ORIGIN;

  try {
    // `.origin` normalises away paths, trailing slashes, and default ports, so
    // callers can join paths without doubling separators.
    return new URL(raw).origin;
  } catch {
    return FALLBACK_ORIGIN;
  }
}

/** Absolute URL for a site-relative path. */
export function absoluteUrl(path: string): string {
  return new URL(path, siteUrl()).toString();
}
