import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  authUrlForBilling,
  BILLING_CALLBACK_PATH,
} from "@/lib/marketing/authLinks";

describe("authUrlForBilling", () => {
  it("routes register through auth with a billing callback", () => {
    assert.equal(
      authUrlForBilling("register"),
      "/auth?mode=register&callbackUrl=%2Fbilling",
    );
  });

  it("routes login through auth with a billing callback", () => {
    assert.equal(authUrlForBilling("login"), "/auth?callbackUrl=%2Fbilling");
  });

  it("uses the billing page as the canonical upgrade destination", () => {
    assert.equal(BILLING_CALLBACK_PATH, "/billing");
  });
});
