import { CapabilitySpotlight } from "@/components/marketing/CapabilitySpotlight";
import { CareerDiscoverySection } from "@/components/marketing/CareerDiscoverySection";
import { CheckupInvite } from "@/components/marketing/CheckupInvite";
import { ClosingCta } from "@/components/marketing/ClosingCta";
import { ComparisonSection } from "@/components/marketing/ComparisonSection";
import { FaqSection } from "@/components/marketing/FaqSection";
import { IntroOverlay } from "@/components/marketing/IntroOverlay";
import { JourneySection } from "@/components/marketing/JourneySection";
import { KeywordScanDemo } from "@/components/marketing/KeywordScanDemo";
import { MarketingHero } from "@/components/marketing/MarketingHero";
import { PricingSection } from "@/components/marketing/PricingSection";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
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
      <IntroOverlay />
      <ScrollReveal>
        <CareerDiscoverySection />
      </ScrollReveal>
      <JourneySection />
      <ComparisonSection />
      {/* Demo the audit, then invite the visitor to run the real one. */}
      <KeywordScanDemo />
      <CheckupInvite />
      <ScrollReveal>
        <CapabilitySpotlight />
      </ScrollReveal>
      <ScrollReveal>
        <PricingSection pricing={pricing} startingCredits={startingCredits} />
      </ScrollReveal>
      <FaqSection startingCredits={startingCredits} />
      <ClosingCta startingCredits={startingCredits} />
    </main>
  );
}
