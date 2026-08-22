import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import type { BillingPricesResponse } from "@/lib/api";
import {
  formatPlanPrice,
  isPlanPriceSynced,
  landingPlansHaveSyncedPrice,
  planCycleSuffix,
  planHighlights,
  selectLandingPlans,
} from "@/lib/marketing/pricing";
import {
  FINE_PRINT,
  INLINE_CTA,
  SECTION,
  SECTION_HEADING,
  SECTION_SUBHEADING,
} from "./styles";

export function PricingSection({
  pricing,
  startingCredits,
}: {
  pricing: BillingPricesResponse | null;
  startingCredits: number;
}) {
  const currency = pricing?.currency ?? "USD";
  const landingPlans = selectLandingPlans(pricing);
  const showTierGrid = landingPlans.length > 0;
  const showAnySyncedPrice = landingPlansHaveSyncedPrice(landingPlans);

  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Start free, upgrade only if it works</h2>
      <p className={SECTION_SUBHEADING}>
        Platform AI is included on every plan &mdash; there are no API keys to
        configure and nothing to bring.
      </p>

      <div className="grid grid-cols-1 items-start gap-5 sm:grid-cols-2 xl:grid-cols-5">
        <div className="rounded-xl border border-emerald-200 bg-emerald-50/50 p-5 dark:border-emerald-700/50 dark:bg-emerald-900/20">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">Free</h3>
          <p className="mt-2 text-3xl font-bold text-slate-900 dark:text-white">
            $0
          </p>
          <p className={`${FINE_PRINT} mt-1`}>No credit card</p>
          <ul className="mt-4 space-y-2">
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
        </div>

        {showTierGrid ? (
          landingPlans.map((plan) => {
            const price = isPlanPriceSynced(plan)
              ? formatPlanPrice(plan.amount_cents, currency)
              : null;
            const highlighted = plan.code === "monthly_pro";

            return (
              <div
                key={plan.code}
                className={`relative rounded-xl border p-5 ${
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
                {price ? (
                  <>
                    <p className="mt-2 flex items-baseline gap-1.5">
                      <span className="text-3xl font-bold text-slate-900 dark:text-white">
                        {price}
                      </span>
                      <span className="text-xs text-slate-600 dark:text-slate-400">
                        {planCycleSuffix(plan.cycle)}
                      </span>
                    </p>
                    <p className={`${FINE_PRINT} mt-1`}>
                      {plan.code === "weekly"
                        ? "Billed weekly"
                        : plan.cycle === "yearly"
                          ? "Billed yearly"
                          : "Billed monthly"}
                    </p>
                  </>
                ) : (
                  <p className={`${FINE_PRINT} mt-3 leading-relaxed`}>
                    Price shown at checkout after you sign in &mdash; never
                    advertised as free before Stripe sync completes.
                  </p>
                )}
                <ul className="mt-4 space-y-2">
                  {planHighlights(plan).map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-amber-700 dark:text-amber-400" />
                      <span className="text-xs leading-relaxed text-slate-700 dark:text-slate-300">
                        {item}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        ) : (
          <div className="rounded-xl border border-slate-300 bg-slate-100/40 p-5 sm:col-span-2 xl:col-span-4 dark:border-slate-700 dark:bg-slate-800/40">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              Paid plans
            </h3>
            <p className="mt-2 text-sm leading-relaxed text-slate-600 dark:text-slate-400">
              Paid tiers add a weekly or monthly resume allowance plus expanded
              job search, fit scoring, Whisper voice, and more Career Watch
              companies. Current prices are shown on the billing page once you
              have an account.
            </p>
            <Link href="/auth?mode=register" className={`${INLINE_CTA} mt-4`}>
              See plans and pricing
              <ArrowRight aria-hidden className="h-4 w-4" />
            </Link>
          </div>
        )}
      </div>

      {showTierGrid && showAnySyncedPrice && (
        <p className={`mt-6 text-center ${FINE_PRINT}`}>
          Prices above come from live billing config. Discounted yearly billing
          is available on the billing page after you sign in.
        </p>
      )}
    </section>
  );
}
