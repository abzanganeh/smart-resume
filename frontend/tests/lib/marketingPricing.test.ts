import { afterEach, describe, it, mock } from "node:test";
import assert from "node:assert/strict";
import type { BillingPlan, BillingPricesResponse } from "@/lib/api";
import {
  fetchPublicPricing,
  formatPlanPrice,
  isPlanPriceSynced,
  planCycleSuffix,
  planHighlights,
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

function limits(
  overrides: Partial<NonNullable<BillingPlan["limits"]>> = {},
): NonNullable<BillingPlan["limits"]> {
  return {
    resumes_per_period: 50,
    searches_per_period: 100,
    fit_analyses_per_period: 50,
    whisper_uses_per_period: 5,
    career_watch_companies: 10,
    ...overrides,
  };
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

  it("rejects a non-numeric amount from a malformed payload", () => {
    // Without this, a string amount would pass `> 0` by coercion, then sort by
    // string subtraction and format as "$NaN".
    const malformed = plan({
      amount_cents: "1999" as unknown as number,
    });
    assert.equal(isPlanPriceSynced(malformed), false);
    assert.equal(
      isPlanPriceSynced(plan({ amount_cents: NaN })),
      false,
    );
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

describe("selectPublicPlans on an unsynced catalog", () => {
  it("returns nothing when no plan has a real price", () => {
    // This is the state of a fresh environment before price_sync runs. The
    // section must fall back rather than show a grid of $0.00 cards.
    assert.deepEqual(
      selectPublicPlans(
        payload([
          plan({ code: "monthly_pro", amount_cents: 0 }),
          plan({ code: "monthly_plus", amount_cents: 0 }),
        ]),
        "monthly",
      ),
      [],
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
    assert.equal(formatPlanPrice(NaN, "USD"), null);
  });

  it("falls back to USD instead of throwing on a bad currency code", () => {
    // Intl.NumberFormat raises RangeError on a malformed code, and this value
    // comes from the API response — throwing here would 500 the public page.
    assert.equal(formatPlanPrice(1999, "not-a-currency"), "$19.99");
    assert.equal(formatPlanPrice(1999, ""), "$19.99");
  });
});

describe("planHighlights", () => {
  it("returns nothing when the API omits limits", () => {
    assert.deepEqual(planHighlights(plan({ limits: null })), []);
  });

  it("lists the per-period allowances", () => {
    const out = planHighlights(plan({ limits: limits() }));
    assert.ok(out.includes("50 tailored resumes & cover letters"));
    assert.ok(out.includes("100 job searches"));
    assert.ok(out.includes("50 fit analyses"));
  });

  it("describes a null Whisper cap as fair use", () => {
    const out = planHighlights(
      plan({ limits: limits({ whisper_uses_per_period: null }) }),
    );
    assert.ok(out.includes("Whisper voice — fair use"));
  });

  it("omits Whisper entirely when the tier has none", () => {
    const out = planHighlights(
      plan({ limits: limits({ whisper_uses_per_period: 0 }) }),
    );
    assert.equal(
      out.some((line) => line.includes("Whisper")),
      false,
    );
  });

  it("singularises a one-company Career Watch allowance", () => {
    const single = planHighlights(
      plan({ limits: limits({ career_watch_companies: 1 }) }),
    );
    assert.ok(single.includes("1 Career Watch company"));

    const many = planHighlights(
      plan({ limits: limits({ career_watch_companies: 30 }) }),
    );
    assert.ok(many.includes("30 Career Watch companies"));
  });
});

describe("planCycleSuffix", () => {
  it("labels each supported cycle", () => {
    assert.equal(planCycleSuffix("weekly"), "/ week");
    assert.equal(planCycleSuffix("monthly"), "/ month");
    assert.equal(planCycleSuffix("yearly"), "/ year");
  });
});

describe("fetchPublicPricing", () => {
  afterEach(() => {
    mock.restoreAll();
  });

  it("returns the payload when the public endpoint responds", async () => {
    const body = payload([plan()]);
    mock.method(globalThis, "fetch", async () =>
      ({ ok: true, json: async () => body }) as Response,
    );

    const result = await fetchPublicPricing();
    assert.deepEqual(result, body);
  });

  it("returns null when the endpoint errors", async () => {
    mock.method(globalThis, "fetch", async () => ({ ok: false }) as Response);
    assert.equal(await fetchPublicPricing(), null);
  });

  it("returns null when the backend is unreachable", async () => {
    mock.method(globalThis, "fetch", async () => {
      throw new Error("ECONNREFUSED");
    });
    assert.equal(await fetchPublicPricing(), null);
  });

  it("returns null on a malformed payload rather than trusting it", async () => {
    mock.method(globalThis, "fetch", async () =>
      ({ ok: true, json: async () => ({ version: "1" }) }) as Response,
    );
    assert.equal(await fetchPublicPricing(), null);
  });
});
