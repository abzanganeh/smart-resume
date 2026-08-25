import Link from "next/link";
import { ArrowRight } from "lucide-react";
import type { BillingPricesResponse } from "@/lib/api";
import { authUrlForBilling } from "@/lib/marketing/authLinks";
import {
  landingPlansHaveSyncedPrice,
  resolveLandingPlans,
} from "@/lib/marketing/pricing";
import { PricingTierGrid } from "@/components/marketing/PricingTierGrid";
import {
  FINE_PRINT,
  PRIMARY_CTA,
  SECONDARY_CTA,
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
  const landingPlans = resolveLandingPlans(pricing);
  const showAnySyncedPrice = landingPlansHaveSyncedPrice(landingPlans);
  const billingRegisterUrl = authUrlForBilling("register");
  const billingLoginUrl = authUrlForBilling("login");

  return (
    <section id="pricing" className={`${SECTION} scroll-mt-24 pb-24`}>
      <h2 className={SECTION_HEADING}>Start free, upgrade only if it works</h2>
      <p className={SECTION_SUBHEADING}>
        Compare every tier side by side. Sign in with Google, GitHub, Microsoft,
        LinkedIn, or email, then pick your plan on the billing page.
      </p>

      <PricingTierGrid initialPricing={pricing} startingCredits={startingCredits} />

      <div className="mt-10 flex flex-col items-center gap-4">
        <div className="flex flex-col items-stretch gap-3 sm:flex-row sm:items-center sm:justify-center">
          <Link href={billingRegisterUrl} className={PRIMARY_CTA}>
            Create account &amp; choose a plan
            <ArrowRight aria-hidden className="h-5 w-5" />
          </Link>
          <Link href={billingLoginUrl} className={SECONDARY_CTA}>
            Sign in to upgrade
          </Link>
        </div>
        {showAnySyncedPrice ? (
          <p className={`text-center ${FINE_PRINT}`}>
            Prices above come from live billing config. Discounted yearly billing
            is available on the billing page after you sign in.
          </p>
        ) : (
          <p className={`text-center ${FINE_PRINT}`}>
            Dollar amounts are pulled from Stripe via the billing API &mdash; they
            appear here after plan configs are seeded and the price sync job runs.
            Allowances above are always shown so you can compare tiers; checkout
            shows the live price before you pay.
          </p>
        )}
      </div>
    </section>
  );
}
