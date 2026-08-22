/**
 * OWASP A02 baseline response headers (M23 slice A2).
 *
 * CSP ships as Report-Only first so landing motion (M16) violations surface
 * without breaking production. See SECURITY.md for the style-src ratchet plan.
 */

const API_ORIGIN = (() => {
  const raw = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
  try {
    return new URL(raw).origin;
  } catch {
    return "http://localhost:8000";
  }
})();

/** Build the Report-Only CSP directive string. */
export function buildContentSecurityPolicyReportOnly(): string {
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
      key: "Content-Security-Policy-Report-Only",
      value: buildContentSecurityPolicyReportOnly(),
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
