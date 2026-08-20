/**
 * Public pricing helpers for the landing page.
 *
 * Prices are never hardcoded. They come from `GET /api/billing/prices`, which
 * is public and unauthenticated. `bootstrap.py` seeds `PlanConfig.amount_cents`
 * to 0 until the Stripe price sync runs, so 0 means "price unknown" and must
 * never reach the page as a real amount.
 */
import type { BillingPlan, BillingPricesResponse } from "@/lib/api";

export type BillingCycle = BillingPlan["cycle"];

export function isPlanPriceSynced(plan: BillingPlan): boolean {
  return plan.amount_cents > 0;
}

/** Active, price-synced plans for one billing cycle, cheapest first. */
export function selectPublicPlans(
  payload: BillingPricesResponse | null | undefined,
  cycle: BillingCycle,
): BillingPlan[] {
  if (!payload?.plans) {
    return [];
  }
  return payload.plans
    .filter(
      (plan) =>
        plan.cycle === cycle && plan.is_active && isPlanPriceSynced(plan),
    )
    .sort((a, b) => a.amount_cents - b.amount_cents);
}

/** False when prices have not been synced yet, so the section can defer. */
export function hasSyncedPricing(
  payload: BillingPricesResponse | null | undefined,
): boolean {
  return payload?.plans?.some(isPlanPriceSynced) ?? false;
}

/** Formatted amount, or `null` when the price is not known yet. */
export function formatPlanPrice(
  cents: number,
  currency = "USD",
): string | null {
  if (cents <= 0) {
    return null;
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
  }).format(cents / 100);
}

export function planCycleSuffix(cycle: BillingCycle): string {
  switch (cycle) {
    case "daily":
      return "/ day";
    case "weekly":
      return "/ week";
    case "monthly":
      return "/ month";
    case "yearly":
      return "/ year";
  }
}
