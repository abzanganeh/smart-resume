"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { Check } from "lucide-react";
import type { BillingPlan, BillingPricesResponse } from "@/lib/api";
import { authUrlForBilling } from "@/lib/marketing/authLinks";
import {
  formatPlanPrice,
  isPlanPriceSynced,
  landingPlansHaveSyncedPrice,
  planCycleSuffix,
  planHighlights,
  planVolumeTagline,
  resolveLandingPlans,
} from "@/lib/marketing/pricing";
import {
  CUSTOMIZED_TIER_CTA,
  CUSTOMIZED_TIER_DISPLAY_NAME,
  CUSTOMIZED_TIER_HIGHLIGHTS,
  CUSTOMIZED_TIER_PRICE_LABEL,
  CUSTOMIZED_TIER_SUBLINE,
  customizedTierContactHref,
} from "@/lib/marketing/customizedTier";
import { FINE_PRINT, TIER_CTA, TIER_CTA_HIGHLIGHT } from "./styles";

function tierCtaLabel(plan: BillingPlan): string {
  return `Choose ${plan.display_name}`;
}

function TierPriceBlock({
  plan,
  price,
}: {
  plan: BillingPlan;
  price: string | null;
}) {
  return (
    <div className="mt-2 min-h-[4.75rem]">
      {price ? (
        <>
          <p className="flex items-baseline gap-1.5">
            <span className="text-3xl font-bold text-slate-900 dark:text-white">
              {price}
            </span>
            <span className="text-xs text-slate-600 dark:text-slate-400">
              {planCycleSuffix(plan.cycle)}
            </span>
          </p>
          <p className={`${FINE_PRINT} mt-1`}>
            {plan.trial_days
              ? `${plan.trial_days}-day trial`
              : plan.code === "weekly"
                ? "Billed weekly"
                : "Billed monthly"}
          </p>
        </>
      ) : (
        <p className={`${FINE_PRINT} leading-relaxed`}>
          Price loads from billing once Stripe sync completes
        </p>
      )}
    </div>
  );
}

export function PricingTierGrid({
  initialPricing,
  startingCredits,
}: {
  initialPricing: BillingPricesResponse | null;
  startingCredits: number;
}) {
  const [pricing, setPricing] = useState(initialPricing);
  const currency = pricing?.currency ?? "USD";
  const landingPlans = resolveLandingPlans(pricing);
  const billingRegisterUrl = authUrlForBilling("register");

  useEffect(() => {
    if (landingPlansHaveSyncedPrice(resolveLandingPlans(initialPricing))) {
      return;
    }

    const base = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
    let cancelled = false;

    void fetch(`${base}/api/billing/prices`, { cache: "no-store" })
      .then(async (res) => (res.ok ? ((await res.json()) as BillingPricesResponse) : null))
      .then((data) => {
        if (!cancelled && data?.plans?.length) {
          setPricing(data);
        }
      })
      .catch(() => {
        // Keep SSR/fallback tiers visible.
      });

    return () => {
      cancelled = true;
    };
  }, [initialPricing]);

  return (
    <div className="-mx-6 overflow-x-auto px-6 pb-2 lg:mx-0 lg:overflow-visible lg:px-0">
      <div className="grid w-max min-w-full auto-cols-[min(15.5rem,calc(100vw-3rem))] grid-flow-col items-stretch gap-4 lg:w-auto lg:auto-cols-auto lg:grid-flow-row lg:grid-cols-6">
        <div className="flex h-full flex-col rounded-xl border border-emerald-200 bg-emerald-50/50 p-5 dark:border-emerald-700/50 dark:bg-emerald-900/20">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">Free</h3>
          <div className="mt-2 min-h-[4.75rem]">
            <p className="text-3xl font-bold text-slate-900 dark:text-white">$0</p>
            <p className={`${FINE_PRINT} mt-1`}>No credit card</p>
          </div>
          <ul className="mt-4 flex-1 space-y-2">
            {[
              `${startingCredits} AI credits at signup`,
              "Master resume & Story Mode",
              "Career discovery — 10 fitted titles",
              "Resume checkup, no account needed",
              "Application tracker",
            ].map((item) => (
              <li key={item} className="flex items-start gap-2">
                <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-emerald-700 dark:text-emerald-400" />
                <span className="text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                  {item}
                </span>
              </li>
            ))}
          </ul>
          <Link href="/auth?mode=register" className={`${TIER_CTA} mt-auto`}>
            Start free
          </Link>
        </div>

        {landingPlans.map((plan) => {
          const price = isPlanPriceSynced(plan)
            ? formatPlanPrice(plan.amount_cents, currency)
            : null;
          const highlighted = plan.code === "monthly_pro";

          return (
            <div
              key={plan.code}
              className={`relative flex h-full flex-col rounded-xl border p-5 ${
                highlighted
                  ? "border-amber-400/60 bg-amber-50/40 ring-1 ring-amber-400/30 dark:border-amber-500/40 dark:bg-amber-950/20"
                  : "border-slate-300 bg-slate-100/40 dark:border-slate-700 dark:bg-slate-800/40"
              }`}
            >
              {highlighted && (
                <span className="absolute -top-2.5 left-4 rounded-full bg-amber-400 px-2 py-0.5 text-[10px] font-bold text-slate-900">
                  Most popular
                </span>
              )}
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                {plan.display_name}
              </h3>
              {planVolumeTagline(plan) ? (
                <p className={`${FINE_PRINT} mt-0.5`}>{planVolumeTagline(plan)}</p>
              ) : null}
              <TierPriceBlock plan={plan} price={price} />
              <ul className="mt-4 flex-1 space-y-2">
                {planHighlights(plan).map((item) => (
                  <li key={item} className="flex items-start gap-2">
                    <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
                    <span className="text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                      {item}
                    </span>
                  </li>
                ))}
              </ul>
              <Link
                href={billingRegisterUrl}
                className={`${highlighted ? TIER_CTA_HIGHLIGHT : TIER_CTA} mt-auto`}
              >
                {tierCtaLabel(plan)}
              </Link>
            </div>
          );
        })}

        <div className="flex h-full flex-col rounded-xl border border-violet-300/60 bg-violet-50/30 p-5 dark:border-violet-700/50 dark:bg-violet-950/20">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">
            {CUSTOMIZED_TIER_DISPLAY_NAME}
          </h3>
          <div className="mt-2 min-h-[4.75rem]">
            <p className="text-3xl font-bold text-slate-900 dark:text-white">
              {CUSTOMIZED_TIER_PRICE_LABEL}
            </p>
            <p className={`${FINE_PRINT} mt-1`}>{CUSTOMIZED_TIER_SUBLINE}</p>
          </div>
          <ul className="mt-4 flex-1 space-y-2">
            {CUSTOMIZED_TIER_HIGHLIGHTS.map((item) => (
              <li key={item} className="flex items-start gap-2">
                <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-violet-700 dark:text-violet-400" />
                <span className="text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                  {item}
                </span>
              </li>
            ))}
          </ul>
          <a href={customizedTierContactHref()} className={`${TIER_CTA} mt-auto`}>
            {CUSTOMIZED_TIER_CTA}
          </a>
        </div>
      </div>
    </div>
  );
}
