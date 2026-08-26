import { HeroScrollExperience } from "@/components/marketing/HeroScrollExperience";

/**
 * Pinned hero only. The post-hero sequence (CTA → roles → proof) is rendered
 * from page.tsx, inside the shared landing-scroll-band wrapper, so its
 * background stays consistent with the rest of the middle scroll.
 */
export function MarketingHero() {
  return (
    <div className="marketing-hero">
      <section className="marketing-hero-ambient relative w-full">
        <HeroScrollExperience />
      </section>
    </div>
  );
}
