/**
 * OWASP A02 baseline response headers (M23 slice A2, E5 nonce ratchet).
 *
 * CSP is generated per request in proxy.ts with a cryptographic nonce used by
 * ``script-src``. ``style-src`` intentionally omits the nonce and keeps
 * ``'unsafe-inline'``: no ``<style>`` element in the app is nonced, and CSP-3
 * ignores ``'unsafe-inline'`` for a directive that also lists a nonce, which
 * would block every React ``style={{}}`` attribute (see SECURITY.md).
 */

const API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

const TURNSTILE_ORIGIN = "https://challenges.cloudflare.com";

export type CspOptions = {
  nonce?: string;
  /** Override NODE_ENV detection (unit tests). */
  production?: boolean;
};

/** Build the enforcing CSP directive string. */
export function buildContentSecurityPolicy(options: CspOptions = {}): string {
  const isDev =
    options.production === true
      ? false
      : options.production === false
        ? true
        : process.env.NODE_ENV !== "production";
  const nonce = options.nonce;

  let scriptSrc: string;
  if (nonce && !isDev) {
    scriptSrc = [
      "script-src 'self'",
      `'nonce-${nonce}'`,
      "'strict-dynamic'",
      TURNSTILE_ORIGIN,
    ].join(" ");
  } else if (nonce && isDev) {
    scriptSrc = [
      "script-src 'self'",
      `'nonce-${nonce}'`,
      "'unsafe-inline'",
      "'unsafe-eval'",
      TURNSTILE_ORIGIN,
    ].join(" ");
  } else {
    scriptSrc = isDev
      ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
      : "script-src 'self' 'unsafe-inline'";
  }

  const styleSrc = "style-src 'self' 'unsafe-inline'";

  const directives = [
    "default-src 'self'",
    scriptSrc,
    styleSrc,
    "img-src 'self' data: blob: https://api.qrserver.com",
    "font-src 'self'",
    `connect-src 'self' ${API_ORIGIN}`,
    `frame-src 'self' ${TURNSTILE_ORIGIN}`,
    "frame-ancestors 'none'",
    "base-uri 'self'",
    "form-action 'self'",
    "object-src 'none'",
  ];

  if (!isDev) {
    directives.push("upgrade-insecure-requests");
  }

  return directives.join("; ");
}

const PERMISSIONS_POLICY =
  "accelerometer=(), camera=(), geolocation=(), gyroscope=(), magnetometer=(), microphone=(), payment=(self), usb=()";

/** Non-CSP security headers (CSP is set per request in proxy.ts). */
export function securityResponseHeaders(): { key: string; value: string }[] {
  const headers: { key: string; value: string }[] = [
    { key: "X-Content-Type-Options", value: "nosniff" },
    { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
    { key: "X-Frame-Options", value: "DENY" },
    { key: "Permissions-Policy", value: PERMISSIONS_POLICY },
  ];

  if (process.env.NODE_ENV === "production") {
    headers.push({
      key: "Strict-Transport-Security",
      value: "max-age=63072000; includeSubDomains; preload",
    });
  }

  return headers;
}
