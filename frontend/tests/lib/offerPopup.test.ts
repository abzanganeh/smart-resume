import assert from "node:assert/strict";
import { describe, it } from "node:test";
import {
  defaultCheckoutPlanCode,
  formatOfferCountdown,
  hasShownOfferPopupThisSession,
  isOfferPopupPathBlocked,
  markOfferPopupShown,
  offerCountdownParts,
  pickPopupOffer,
  type BillingPopupOffer,
} from "../../lib/offerPopup";

const sampleOffer = (overrides: Partial<BillingPopupOffer> = {}): BillingPopupOffer => ({
  code: "SAVE40",
  grant_type: "price_discount",
  expires_at: "2099-01-01T00:00:00.000Z",
  is_active: true,
  is_redeemable: true,
  applicable_plan_codes: ["monthly_pro", "yearly_pro"],
  display_name: "40% off Pro",
  headline: "Limited-time upgrade",
  popup_enabled: true,
  popup_triggers: ["exit_intent", "post_exhaustion"],
  ...overrides,
});

describe("offerPopup helpers", () => {
  it("blocks landing and auth paths for exit-intent popups", () => {
    assert.equal(isOfferPopupPathBlocked("/"), true);
    assert.equal(isOfferPopupPathBlocked("/auth"), true);
    assert.equal(isOfferPopupPathBlocked("/dashboard"), false);
  });

  it("picks the first redeemable offer for a trigger", () => {
    const offers = [
      sampleOffer({ code: "A", popup_triggers: ["exit_intent"] }),
      sampleOffer({ code: "B", popup_triggers: ["post_exhaustion"] }),
    ];
    assert.equal(pickPopupOffer(offers, "post_exhaustion")?.code, "B");
    assert.equal(pickPopupOffer(offers, "exit_intent")?.code, "A");
  });

  it("formats countdown from server deadline", () => {
    const now = Date.parse("2026-01-01T00:00:00.000Z");
    const parts = offerCountdownParts("2026-01-01T00:01:05.000Z", now);
    assert.deepEqual(parts, { days: 0, hours: 0, minutes: 1, seconds: 5 });
    assert.equal(
      formatOfferCountdown("2026-01-01T00:01:05.000Z", now),
      "00:01:05",
    );
  });

  it("defaults checkout plan to monthly_pro when available", () => {
    assert.equal(defaultCheckoutPlanCode(sampleOffer()), "monthly_pro");
  });

  it("tracks once-per-session popup dismissal state", () => {
    const storage = new Map<string, string>();
    const originalWindow = globalThis.window;
    const originalSessionStorage = globalThis.sessionStorage;
    Object.defineProperty(globalThis, "window", {
      configurable: true,
      value: globalThis,
    });
    Object.defineProperty(globalThis, "sessionStorage", {
      configurable: true,
      value: {
        getItem: (key: string) => storage.get(key) ?? null,
        setItem: (key: string, value: string) => {
          storage.set(key, value);
        },
      },
    });
    try {
      assert.equal(hasShownOfferPopupThisSession(), false);
      markOfferPopupShown();
      assert.equal(hasShownOfferPopupThisSession(), true);
    } finally {
      Object.defineProperty(globalThis, "window", {
        configurable: true,
        value: originalWindow,
      });
      Object.defineProperty(globalThis, "sessionStorage", {
        configurable: true,
        value: originalSessionStorage,
      });
    }
  });
});
