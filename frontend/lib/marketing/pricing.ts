/**
 * Public pricing helpers for the landing page.
 *
 * Prices are never hardcoded. They come from `GET /api/billing/prices`, which
 * is public and unauthenticated. `bootstrap.py` seeds `PlanConfig.amount_cents`
 * to 0 until the Stripe price sync runs, so 0 means "price unknown" and must
 * never reach the page as a real amount.
 *
 * Everything here treats the payload as untrusted input: it crosses the network
 * and is rendered during SSR of a public page, so a malformed field must
 * degrade to a fallback rather than throw and 500 the whole route.
 */
import type { BillingPlan, BillingPricesResponse } from "@/lib/api";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

/** Keep in step with `lib/freeTier.ts` so both public fetches behave alike. */
const REVALIDATE_SECONDS = 60;
const TIMEOUT_MS = 2_000;

const CURRENCY_CODE = /^[A-Za-z]{3}$/;

export type BillingCycle = BillingPlan["cycle"];

/**
 * Read the public price catalog for unauthenticated visitors.
 *
 * Returns `null` on any failure so the landing page can fall back to a
 * "see plans" link instead of rendering a broken or invented price. The
 * timeout matters because this is awaited during SSR on every request: a
 * backend that accepts the connection and stalls would otherwise hang the
 * public page indefinitely.
 */
export async function fetchPublicPricing(): Promise<BillingPricesResponse | null> {
  try {
    const res = await fetch(`${BASE}/api/billing/prices`, {
      next: { revalidate: REVALIDATE_SECONDS },
      signal: AbortSignal.timeout(TIMEOUT_MS),
    });
    if (!res.ok) {
      return null;
    }
    const data = (await res.json()) as unknown;
    if (
      typeof data !== "object" ||
      data === null ||
      !Array.isArray((data as BillingPricesResponse).plans)
    ) {
      return null;
    }
    return data as BillingPricesResponse;
  } catch {
    return null;
  }
}

/**
 * True only for a plan carrying a real, usable price.
 *
 * `Number.isFinite` matters as much as the `> 0` check: a string amount from a
 * malformed payload would pass `> 0` by coercion, then sort by string
 * subtraction and format as "$NaN".
 */
export function isPlanPriceSynced(plan: BillingPlan): boolean {
  return Number.isFinite(plan.amount_cents) && plan.amount_cents > 0;
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

/**
 * Formatted amount, or `null` when the price is not known or not usable.
 *
 * An unrecognised currency falls back to USD rather than throwing —
 * `Intl.NumberFormat` raises `RangeError` on a malformed code, and the value
 * originates from the API response.
 */
export function formatPlanPrice(
  cents: number,
  currency = "USD",
): string | null {
  if (!Number.isFinite(cents) || cents <= 0) {
    return null;
  }
  const safeCurrency = CURRENCY_CODE.test(currency) ? currency : "USD";
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: safeCurrency,
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

/**
 * Marketing bullet list for a plan card, derived from the per-period
 * allowances the public endpoint already publishes.
 */
export function planHighlights(plan: BillingPlan): string[] {
  const limits = plan.limits;
  if (!limits) {
    return [];
  }
  const out = [
    `${limits.resumes_per_period} tailored resumes & cover letters`,
    `${limits.searches_per_period} job searches`,
    `${limits.fit_analyses_per_period} fit analyses`,
  ];
  // null means fair use (Premium); 0 means the tier has no Whisper at all.
  if (limits.whisper_uses_per_period === null) {
    out.push("Whisper voice — fair use");
  } else if (limits.whisper_uses_per_period > 0) {
    out.push(`${limits.whisper_uses_per_period} Whisper voice sessions`);
  }
  out.push(
    limits.career_watch_companies === 1
      ? "1 Career Watch company"
      : `${limits.career_watch_companies} Career Watch companies`,
  );
  return out;
}
