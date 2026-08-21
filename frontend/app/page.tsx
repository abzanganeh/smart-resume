import { CapabilitySpotlight } from "@/components/marketing/CapabilitySpotlight";
import { CareerDiscoverySection } from "@/components/marketing/CareerDiscoverySection";
import { CheckupInvite } from "@/components/marketing/CheckupInvite";
import { ClosingCta } from "@/components/marketing/ClosingCta";
import { ComparisonSection } from "@/components/marketing/ComparisonSection";
import { FaqSection } from "@/components/marketing/FaqSection";
import { JourneySection } from "@/components/marketing/JourneySection";
import { KeywordScanDemo } from "@/components/marketing/KeywordScanDemo";
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
      {/* Demo the audit, then invite the visitor to run the real one. */}
      <KeywordScanDemo />
      <CheckupInvite />
      <CapabilitySpotlight />
      <PricingSection pricing={pricing} startingCredits={startingCredits} />
      <PlatformDetails />
      <FaqSection startingCredits={startingCredits} />
      <ClosingCta startingCredits={startingCredits} />
    </main>
  );
}
