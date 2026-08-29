import assert from "node:assert/strict";
import { describe, it } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { PRODUCT_NAME, SALES_INQUIRY_EMAIL } from "@/lib/brand";
import { PricingTierGrid } from "@/components/marketing/PricingTierGrid";
import {
  CUSTOMIZED_TIER_CTA,
  CUSTOMIZED_TIER_DISPLAY_NAME,
  CUSTOMIZED_TIER_HIGHLIGHTS,
  CUSTOMIZED_TIER_PRICE_LABEL,
  customizedTierContactHref,
} from "@/lib/marketing/customizedTier";
import { planVolumeTagline } from "@/lib/marketing/pricing";
import type { BillingPlan } from "@/lib/api";

function plan(overrides: Partial<BillingPlan> = {}): BillingPlan {
  return {
    code: "monthly_pro",
    display_name: "Pro",
    cycle: "monthly",
    amount_cents: 1999,
    trial_days: null,
    stripe_price_id: "price_test",
    is_active: true,
    features: ["resume_tailor"],
    limits: null,
    ...overrides,
  };
}

describe("customizedTierContactHref", () => {
  it("builds a mailto with sales email and encoded subject", () => {
    const href = customizedTierContactHref();
    assert.ok(href.startsWith(`mailto:${SALES_INQUIRY_EMAIL}?subject=`));
    const subject = decodeURIComponent(href.split("subject=")[1] ?? "");
    assert.equal(subject, `${PRODUCT_NAME} Customized plan inquiry`);
  });
});

describe("customized tier catalog", () => {
  it("exposes display metadata without a numeric price", () => {
    assert.equal(CUSTOMIZED_TIER_DISPLAY_NAME, "Customized");
    assert.equal(CUSTOMIZED_TIER_PRICE_LABEL, "Custom quote");
    assert.equal(CUSTOMIZED_TIER_CTA, "Contact us");
    assert.ok(
      CUSTOMIZED_TIER_HIGHLIGHTS.some((line) =>
        /not sold through self-serve checkout/i.test(line),
      ),
    );
  });
});

describe("PricingTierGrid customized card", () => {
  it("renders the customized quote card with mailto CTA", () => {
    const html = renderToStaticMarkup(
      <PricingTierGrid initialPricing={null} startingCredits={3} />,
    );
    assert.match(html, new RegExp(`>${CUSTOMIZED_TIER_DISPLAY_NAME}<`));
    assert.match(html, new RegExp(`>${CUSTOMIZED_TIER_PRICE_LABEL}<`));
    assert.match(html, /not sold through self-serve checkout/i);
    assert.match(html, /href="mailto:privacy@zanganehai\.com\?subject=/);
    assert.match(html, new RegExp(`>${CUSTOMIZED_TIER_CTA}<`));
    assert.doesNotMatch(html, /Choose Customized/);
  });
});

describe("planVolumeTagline", () => {
  it("tags Premium as highest volume with same AI quality", () => {
    const tagline = planVolumeTagline(
      plan({ code: "monthly_premium", display_name: "Premium" }),
    );
    assert.match(tagline ?? "", /highest volume/i);
    assert.match(tagline ?? "", /same ai quality/i);
  });

  it("returns null for other paid tiers", () => {
    assert.equal(planVolumeTagline(plan({ code: "monthly_pro" })), null);
    assert.equal(planVolumeTagline(plan({ code: "weekly", cycle: "weekly" })), null);
    assert.equal(planVolumeTagline(plan({ code: "monthly_plus" })), null);
  });
});
