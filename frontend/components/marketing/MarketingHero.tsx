import { HeroScrollExperience } from "@/components/marketing/HeroScrollExperience";
import { PostHeroScrollSequence } from "@/components/marketing/PostHeroScrollSequence";

export function MarketingHero({ startingCredits }: { startingCredits: number }) {
  return (
    <div className="marketing-hero">
      <section className="marketing-hero-ambient relative w-full">
        <HeroScrollExperience />
      </section>

      <PostHeroScrollSequence startingCredits={startingCredits} />
    </div>
  );
}
