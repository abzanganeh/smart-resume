/**
 * OWASP A02 baseline response headers (M23 slice A2, enforced E3 ratchet).
 *
 * CSP is enforcing on production builds; ``style-src 'unsafe-inline'`` remains
 * an accepted risk for M16 landing motion until nonce/hash migration.
 */

const API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

/** Build the enforcing CSP directive string. */
export function buildContentSecurityPolicy(): string {
  const isDev = process.env.NODE_ENV !== "production";

  const scriptSrc = isDev
    ? "script-src 'self' 'unsafe-inline' 'unsafe-eval'"
    : "script-src 'self' 'unsafe-inline'";

  const directives = [
    "default-src 'self'",
    scriptSrc,
    // M16 landing motion sets CSS custom properties inline; nonce/hash is the
    // enforce-phase goal (see SECURITY.md accepted-risk row).
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob: https://api.qrserver.com",
    "font-src 'self'",
    `connect-src 'self' ${API_ORIGIN}`,
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

/** Header pairs applied to every public and authenticated route. */
export function securityResponseHeaders(): { key: string; value: string }[] {
  const headers: { key: string; value: string }[] = [
    {
      key: "Content-Security-Policy",
      value: buildContentSecurityPolicy(),
    },
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
