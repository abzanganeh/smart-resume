import { describe, it } from "node:test";
import assert from "node:assert/strict";
import type { BillingPlan, BillingPricesResponse } from "@/lib/api";
import {
  formatPlanPrice,
  hasSyncedPricing,
  isPlanPriceSynced,
  planCycleSuffix,
  selectPublicPlans,
} from "@/lib/marketing/pricing";

function plan(overrides: Partial<BillingPlan> = {}): BillingPlan {
  return {
    code: "monthly_pro",
    display_name: "Pro",
    cycle: "monthly",
    amount_cents: 1999,
    trial_days: 7,
    stripe_price_id: "price_test",
    is_active: true,
    features: ["resume_tailor"],
    limits: null,
    ...overrides,
  };
}

function payload(plans: BillingPlan[]): BillingPricesResponse {
  return { version: "1", currency: "USD", plans, addons: [] };
}

describe("isPlanPriceSynced", () => {
  it("treats a positive amount as synced", () => {
    assert.equal(isPlanPriceSynced(plan({ amount_cents: 999 })), true);
  });

  it("treats zero as unsynced", () => {
    // bootstrap.py seeds PlanConfig with amount_cents=0 until the Stripe price
    // sync runs, so 0 means "unknown price", never "free".
    assert.equal(isPlanPriceSynced(plan({ amount_cents: 0 })), false);
  });

  it("treats a negative amount as unsynced", () => {
    assert.equal(isPlanPriceSynced(plan({ amount_cents: -100 })), false);
  });
});

describe("selectPublicPlans", () => {
  it("keeps only the requested billing cycle", () => {
    const selected = selectPublicPlans(
      payload([
        plan({ code: "monthly_pro", cycle: "monthly" }),
        plan({ code: "yearly_pro", cycle: "yearly", amount_cents: 19190 }),
      ]),
      "monthly",
    );
    assert.deepEqual(
      selected.map((p) => p.code),
      ["monthly_pro"],
    );
  });

  it("drops inactive plans", () => {
    const selected = selectPublicPlans(
      payload([plan({ is_active: false })]),
      "monthly",
    );
    assert.deepEqual(selected, []);
  });

  it("drops plans whose price has not been synced from Stripe", () => {
    const selected = selectPublicPlans(
      payload([
        plan({ code: "monthly_pro", amount_cents: 1999 }),
        plan({ code: "monthly_plus", amount_cents: 0 }),
      ]),
      "monthly",
    );
    assert.deepEqual(
      selected.map((p) => p.code),
      ["monthly_pro"],
    );
  });

  it("orders plans cheapest first", () => {
    const selected = selectPublicPlans(
      payload([
        plan({ code: "monthly_premium", amount_cents: 4999 }),
        plan({ code: "monthly_pro", amount_cents: 1999 }),
        plan({ code: "monthly_plus", amount_cents: 2999 }),
      ]),
      "monthly",
    );
    assert.deepEqual(
      selected.map((p) => p.code),
      ["monthly_pro", "monthly_plus", "monthly_premium"],
    );
  });

  it("returns an empty list for a null payload", () => {
    assert.deepEqual(selectPublicPlans(null, "monthly"), []);
  });
});

describe("hasSyncedPricing", () => {
  it("is false when every plan is unsynced", () => {
    assert.equal(
      hasSyncedPricing(payload([plan({ amount_cents: 0 })])),
      false,
    );
  });

  it("is false for a null payload", () => {
    assert.equal(hasSyncedPricing(null), false);
  });

  it("is true when at least one plan has a real price", () => {
    assert.equal(
      hasSyncedPricing(
        payload([plan({ amount_cents: 0 }), plan({ amount_cents: 1999 })]),
      ),
      true,
    );
  });
});

describe("formatPlanPrice", () => {
  it("formats cents as a currency amount", () => {
    assert.equal(formatPlanPrice(1999, "USD"), "$19.99");
  });

  it("defaults to USD when no currency is supplied", () => {
    assert.equal(formatPlanPrice(999), "$9.99");
  });

  it("never renders an unsynced plan as a real price", () => {
    assert.equal(formatPlanPrice(0, "USD"), null);
    assert.equal(formatPlanPrice(-5, "USD"), null);
  });
});

describe("planCycleSuffix", () => {
  it("labels each supported cycle", () => {
    assert.equal(planCycleSuffix("weekly"), "/ week");
    assert.equal(planCycleSuffix("monthly"), "/ month");
    assert.equal(planCycleSuffix("yearly"), "/ year");
  });
});
