import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import type { BillingPricesResponse } from "@/lib/api";
import {
  formatPlanPrice,
  planCycleSuffix,
  planHighlights,
  selectPublicPlans,
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
  // selectPublicPlans already drops unsynced plans, so a non-empty list is
  // exactly the condition for showing real prices.
  const monthly = selectPublicPlans(pricing, "monthly");
  const showPrices = monthly.length > 0;

  return (
    <section className={`${SECTION} pb-24`}>
      <h2 className={SECTION_HEADING}>Start free, upgrade only if it works</h2>
      <p className={SECTION_SUBHEADING}>
        Platform AI is included on every plan &mdash; there are no API keys to
        configure and nothing to bring.
      </p>

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-5 items-start">
        <div className="rounded-xl border border-emerald-200 dark:border-emerald-700/50 bg-emerald-50/50 dark:bg-emerald-900/20 p-5">
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
                <Check aria-hidden className="w-3.5 h-3.5 text-emerald-700 dark:text-emerald-400 shrink-0 mt-0.5" />
                <span className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                  {item}
                </span>
              </li>
            ))}
          </ul>
        </div>

        {showPrices ? (
          monthly.map((plan) => {
            const price = formatPlanPrice(plan.amount_cents, currency);
            // Unreachable while selectPublicPlans filters unsynced plans, but
            // the invariant lives two functions away — keep it local so a card
            // can never render a blank price.
            if (!price) {
              return null;
            }
            return (
              <div
                key={plan.code}
                className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-5"
              >
                <h3 className="font-semibold text-slate-900 dark:text-slate-100">
                  {plan.display_name}
                </h3>
                <p className="mt-2 flex items-baseline gap-1.5">
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
                    : "Billed monthly"}
                </p>
                <ul className="mt-4 space-y-2">
                  {planHighlights(plan).map((item) => (
                    <li key={item} className="flex items-start gap-2">
                      <Check aria-hidden className="w-3.5 h-3.5 text-amber-700 dark:text-amber-400 shrink-0 mt-0.5" />
                      <span className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed">
                        {item}
                      </span>
                    </li>
                  ))}
                </ul>
              </div>
            );
          })
        ) : (
          <div className="md:col-span-1 lg:col-span-3 rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-5">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">
              Paid plans
            </h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400 leading-relaxed">
              Paid tiers add a monthly resume allowance plus expanded job
              search, fit scoring, Whisper voice, and more Career Watch
              companies. Current prices are shown on the billing page once you
              have an account.
            </p>
            <Link href="/auth?mode=register" className={`${INLINE_CTA} mt-4`}>
              See plans and pricing
              <ArrowRight aria-hidden className="w-4 h-4" />
            </Link>
          </div>
        )}
      </div>

      {showPrices && (
        <p className={`mt-6 text-center ${FINE_PRINT}`}>
          Monthly prices shown. Weekly and discounted yearly billing are
          available on the billing page after you sign in.
        </p>
      )}
    </section>
  );
}
