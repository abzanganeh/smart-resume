import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  promoRedeemErrorMessage,
  promoRedeemIdempotentMessage,
  promoRedeemSuccessMessage,
} from "@/lib/promoRedeem";

describe("promoRedeem copy", () => {
  it("maps invalid code", () => {
    assert.equal(
      promoRedeemErrorMessage("promo_code_invalid"),
      "That code is not valid.",
    );
  });

  it("maps expired code", () => {
    assert.equal(
      promoRedeemErrorMessage("promo_code_expired"),
      "That code has expired.",
    );
  });

  it("formats success message", () => {
    assert.equal(
      promoRedeemSuccessMessage(5),
      "Code applied — 5 credits added.",
    );
    assert.equal(
      promoRedeemSuccessMessage(1),
      "Code applied — 1 credit added.",
    );
  });

  it("formats idempotent message", () => {
    assert.equal(
      promoRedeemIdempotentMessage(),
      "This code was already applied to your account.",
    );
  });
});
