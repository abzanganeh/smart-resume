import Link from "next/link";
import { ArrowRight, FileSearch, Sparkles } from "lucide-react";
import { ProductScreenshot } from "@/components/brand/ProductScreenshot";
import { HeroStrengthRotator } from "@/components/marketing/HeroStrengthRotator";
import { PRODUCT_NAME } from "@/lib/brand";
import { formatSignupCreditsCopy } from "@/lib/freeTier";
import { FINE_PRINT, PRIMARY_CTA, SECONDARY_CTA } from "./styles";

export function MarketingHero({ startingCredits }: { startingCredits: number }) {
  const creditsLabel = startingCredits === 1 ? "credit" : "credits";

  return (
    <section className="marketing-hero-ambient max-w-5xl mx-auto px-6 pt-6 pb-16">
      <div aria-hidden className="marketing-hero-orb marketing-hero-orb--amber" />
      <div aria-hidden className="marketing-hero-orb marketing-hero-orb--indigo" />
      <div className="relative z-[1] text-center max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-700 dark:text-slate-300 mb-6">
          <Sparkles aria-hidden className="w-4 h-4 text-amber-700 dark:text-amber-400" />
          Company watch · Alerts in minutes · Never fabricates metrics
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-5 leading-tight">
          Name the companies.{" "}
          <span className="text-amber-700 dark:text-amber-400">
            We&rsquo;ll tell you the minute they&rsquo;re hiring.
          </span>
        </h1>
        <HeroStrengthRotator />
        <p className="text-lg sm:text-xl text-slate-600 dark:text-slate-400 mb-3 max-w-2xl mx-auto">
          {PRODUCT_NAME}{" "}
          watches the careers pages you pick &mdash; the
          company&rsquo;s own listings, not a job board &mdash; and tells you
          when a role opens, in minutes rather than days. Then it tailors an
          ATS-optimized resume to it, using only your real experience.
        </p>
      </div>

      {/* CTAs sit above the screenshot so they stay above the fold. */}
      <div className="relative z-[1] mt-8 text-center">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href="/auth?mode=register" className={PRIMARY_CTA}>
            Start your career story
            <ArrowRight aria-hidden className="w-5 h-5" />
          </Link>
          <Link href="/checkup" className={SECONDARY_CTA}>
            <FileSearch aria-hidden className="w-4 h-4" />
            Check a resume free
          </Link>
        </div>
        <p className="mt-4 text-slate-600 dark:text-slate-400 text-sm">
          {formatSignupCreditsCopy(startingCredits)} · No credit card required
        </p>
        <p className={`mt-1 ${FINE_PRINT}`}>
          Free plans watch one company and check it every 30 minutes; paid plans
          watch more, more often. Registering takes about a minute and includes{" "}
          {startingCredits} AI {creditsLabel}. The resume checkup needs no
          account at all.
        </p>
      </div>

      <div className="relative z-[1] mt-10 max-w-4xl mx-auto">
        <ProductScreenshot priority />
      </div>
    </section>
  );
}
