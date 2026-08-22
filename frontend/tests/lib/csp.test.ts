import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { createCspNonce } from "@/lib/csp";
import { buildContentSecurityPolicy } from "@/lib/securityHeaders";

describe("createCspNonce", () => {
  it("returns distinct base64 nonces per call", () => {
    const a = createCspNonce();
    const b = createCspNonce();
    assert.notEqual(a, b);
    assert.match(a, /^[A-Za-z0-9+/=]+$/);
  });

  it("embeds in a valid production CSP", () => {
    const nonce = createCspNonce();
    const csp = buildContentSecurityPolicy({ nonce, production: true });
    assert.ok(csp.includes(`'nonce-${nonce}'`));
  });
});
