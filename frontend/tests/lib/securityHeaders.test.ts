import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildContentSecurityPolicy,
  securityResponseHeaders,
} from "@/lib/securityHeaders";

function headerMap(
  headers: { key: string; value: string }[],
): Map<string, string> {
  return new Map(headers.map((h) => [h.key.toLowerCase(), h.value]));
}

describe("securityResponseHeaders", () => {
  it("declares the OWASP A02 baseline on all routes", () => {
    const map = headerMap(securityResponseHeaders());

    assert.ok(map.has("content-security-policy"));
    assert.equal(map.get("x-content-type-options"), "nosniff");
    assert.equal(map.get("referrer-policy"), "strict-origin-when-cross-origin");
    assert.equal(map.get("x-frame-options"), "DENY");
    assert.ok(map.get("permissions-policy")?.includes("camera=()"));
  });

  it("includes frame-ancestors none in enforcing CSP", () => {
    const csp = buildContentSecurityPolicy();
    assert.match(csp, /frame-ancestors 'none'/);
    assert.match(csp, /style-src 'self' 'unsafe-inline'/);
  });
});
