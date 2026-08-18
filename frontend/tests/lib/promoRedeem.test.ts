import { describe, expect, it } from "vitest";
import {
  promoRedeemErrorMessage,
  promoRedeemSuccessMessage,
} from "@/lib/promoRedeem";

describe("promoRedeem copy", () => {
  it("maps invalid code", () => {
    expect(promoRedeemErrorMessage("promo_code_invalid")).toBe(
      "That code is not valid.",
    );
  });

  it("maps expired code", () => {
    expect(promoRedeemErrorMessage("promo_code_expired")).toBe(
      "That code has expired.",
    );
  });

  it("formats success message", () => {
    expect(promoRedeemSuccessMessage(5)).toBe("Code applied — 5 credits added.");
    expect(promoRedeemSuccessMessage(1)).toBe("Code applied — 1 credit added.");
  });
});
