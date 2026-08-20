import { CapabilityStrip } from "@/components/marketing/CapabilityStrip";
import { CareerDiscoverySection } from "@/components/marketing/CareerDiscoverySection";
import { CheckupInvite } from "@/components/marketing/CheckupInvite";
import { ClosingCta } from "@/components/marketing/ClosingCta";
import { ComparisonSection } from "@/components/marketing/ComparisonSection";
import { JourneySection } from "@/components/marketing/JourneySection";
import { MarketingHero } from "@/components/marketing/MarketingHero";
import { PlatformDetails } from "@/components/marketing/PlatformDetails";
import { PricingSection } from "@/components/marketing/PricingSection";
import { fetchFreeTierStartingCredits } from "@/lib/freeTier";
import { fetchPublicPricing } from "@/lib/marketing/pricing";

export default async function LandingPage() {
  const [startingCredits, pricing] = await Promise.all([
    fetchFreeTierStartingCredits(),
    fetchPublicPricing(),
  ]);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 text-slate-900 dark:text-white">
      <MarketingHero startingCredits={startingCredits} />
      <CareerDiscoverySection />
      <JourneySection />
      <ComparisonSection />
      <CheckupInvite />
      <CapabilityStrip />
      <PricingSection pricing={pricing} startingCredits={startingCredits} />
      <PlatformDetails />
      <ClosingCta startingCredits={startingCredits} />
    </main>
  );
}
