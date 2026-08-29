import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  buildContentSecurityPolicy,
  securityResponseHeaders,
} from "@/lib/securityHeaders";
import { createCspNonce } from "@/lib/csp";
import { isLocalHttpOrigin } from "@/lib/siteUrl";

function headerMap(
  headers: { key: string; value: string }[],
): Map<string, string> {
  return new Map(headers.map((h) => [h.key.toLowerCase(), h.value]));
}

describe("securityResponseHeaders", () => {
  it("declares the OWASP A02 baseline on all routes (CSP excluded — set in proxy)", () => {
    const map = headerMap(securityResponseHeaders());

    assert.equal(map.has("content-security-policy"), false);
    assert.equal(map.get("x-content-type-options"), "nosniff");
    assert.equal(map.get("referrer-policy"), "strict-origin-when-cross-origin");
    assert.equal(map.get("x-frame-options"), "DENY");
    assert.ok(map.get("permissions-policy")?.includes("camera=()"));
  });

  it("uses nonce + strict-dynamic for production script-src", () => {
    const nonce = createCspNonce();
    const csp = buildContentSecurityPolicy({ nonce, production: true });

    assert.match(csp, new RegExp(`script-src 'self' 'nonce-${nonce}' 'strict-dynamic'`));
    assert.doesNotMatch(csp, /script-src[^;]*'unsafe-inline'/);
    assert.match(csp, /style-src 'self' 'unsafe-inline'/);
    assert.doesNotMatch(csp, /style-src[^;]*'nonce-/);
    assert.match(csp, /frame-ancestors 'none'/);
    assert.match(csp, /frame-src 'self' https:\/\/challenges\.cloudflare\.com/);
  });

  it("allows dev eval while still issuing a nonce", () => {
    const nonce = createCspNonce();
    const csp = buildContentSecurityPolicy({ nonce, production: false });

    assert.match(csp, new RegExp(`'nonce-${nonce}'`));
    assert.match(csp, /'unsafe-eval'/);
  });

  it("omits upgrade-insecure-requests for local http site origins", () => {
    assert.equal(isLocalHttpOrigin("http://localhost:3001"), true);
    assert.equal(isLocalHttpOrigin("https://flintapply.com"), false);
    const csp = buildContentSecurityPolicy({
      production: true,
      localHttpSite: true,
    });
    assert.doesNotMatch(csp, /upgrade-insecure-requests/);
  });

  it("keeps upgrade-insecure-requests and HSTS on production HTTPS origins", () => {
    const csp = buildContentSecurityPolicy({
      production: true,
      localHttpSite: false,
    });
    assert.match(csp, /upgrade-insecure-requests/);

    const map = headerMap(
      securityResponseHeaders({ production: true, localHttpSite: false }),
    );
    assert.match(
      map.get("strict-transport-security") ?? "",
      /max-age=63072000/,
    );
  });
});
