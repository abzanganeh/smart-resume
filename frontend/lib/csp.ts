import { randomUUID } from "node:crypto";
import { NextRequest, NextResponse } from "next/server";
import { buildContentSecurityPolicy } from "@/lib/securityHeaders";

export const NONCE_HEADER = "x-nonce";
export const CSP_HEADER = "Content-Security-Policy";

/** Cryptographic nonce for one CSP policy (base64). */
export function createCspNonce(): string {
  return Buffer.from(randomUUID()).toString("base64");
}

/** Build a `NextResponse.next()` with CSP request headers for SSR nonce injection. */
export function nextWithContentSecurityPolicy(
  request: NextRequest,
  nonce: string,
): NextResponse {
  const csp = buildContentSecurityPolicy({ nonce });
  const requestHeaders = new Headers(request.headers);
  requestHeaders.set(NONCE_HEADER, nonce);
  requestHeaders.set(CSP_HEADER, csp);

  const response = NextResponse.next({
    request: { headers: requestHeaders },
  });
  response.headers.set(CSP_HEADER, csp);
  return response;
}

/** Redirect (or other non-SSR) responses still emit enforcing CSP on the response. */
export function redirectWithContentSecurityPolicy(
  url: URL,
  nonce: string,
): NextResponse {
  const csp = buildContentSecurityPolicy({ nonce });
  const response = NextResponse.redirect(url);
  response.headers.set(CSP_HEADER, csp);
  return response;
}
