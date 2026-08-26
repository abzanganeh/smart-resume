import { CapabilitySpotlight } from "@/components/marketing/CapabilitySpotlight";
import { CheckupInvite } from "@/components/marketing/CheckupInvite";
import { ClosingCta } from "@/components/marketing/ClosingCta";
import { ComparisonSection } from "@/components/marketing/ComparisonSection";
import { FaqSection } from "@/components/marketing/FaqSection";
import { IntroOverlay } from "@/components/marketing/IntroOverlay";
import { JourneySection } from "@/components/marketing/JourneySection";
import { KeywordScanDemo } from "@/components/marketing/KeywordScanDemo";
import { MarketingHero } from "@/components/marketing/MarketingHero";
import { PostHeroScrollSequence } from "@/components/marketing/PostHeroScrollSequence";
import { PricingSection } from "@/components/marketing/PricingSection";
import { ScrollReveal } from "@/components/marketing/ScrollReveal";
import { fetchFreeTierStartingCredits } from "@/lib/freeTier";
import { faqEntries, faqJsonLdScript } from "@/lib/marketing/faq";
import { fetchPublicPricing } from "@/lib/marketing/pricing";
import { headers } from "next/headers";

export default async function LandingPage() {
  const [startingCredits, pricing] = await Promise.all([
    fetchFreeTierStartingCredits(),
    fetchPublicPricing(),
  ]);
  const nonce = (await headers()).get("x-nonce") ?? undefined;
  const faqStructuredData = faqJsonLdScript(faqEntries(startingCredits));

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 text-slate-900 dark:text-white">
      <script
        type="application/ld+json"
        nonce={nonce}
        suppressHydrationWarning
        dangerouslySetInnerHTML={{ __html: faqStructuredData }}
      />
      <MarketingHero />
      <IntroOverlay />
      {/*
        Scroll band: one horizontal amber → neutral → sky wash carries the
        eye from the post-hero handoff through the comparison, the pinned
        journey, the live keyword audit, and the checkup invite. Each
        section renders its content in a similarly sized card so container
        position stays stable while the background does the storytelling.
      */}
      <div className="landing-scroll-band relative">
        <PostHeroScrollSequence startingCredits={startingCredits} />
        <ComparisonSection />
        <JourneySection />
        <KeywordScanDemo />
        <CheckupInvite />
      </div>
      <ScrollReveal>
        <PricingSection pricing={pricing} startingCredits={startingCredits} />
      </ScrollReveal>
      <ScrollReveal>
        <CapabilitySpotlight />
      </ScrollReveal>
      <FaqSection startingCredits={startingCredits} />
      <ClosingCta startingCredits={startingCredits} />
    </main>
  );
}
