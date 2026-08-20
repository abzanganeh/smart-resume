import Link from "next/link";
import { ArrowRight, FileSearch, Sparkles } from "lucide-react";
import { ProductScreenshot } from "@/components/brand/ProductScreenshot";
import { formatSignupCreditsCopy } from "@/lib/freeTier";
import { PRIMARY_CTA, SECONDARY_CTA } from "./styles";

export function MarketingHero({ startingCredits }: { startingCredits: number }) {
  const creditsLabel = startingCredits === 1 ? "credit" : "credits";

  return (
    <section className="max-w-5xl mx-auto px-6 pt-6 pb-16">
      <div className="text-center max-w-3xl mx-auto">
        <div className="inline-flex items-center gap-2 bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-700 dark:text-slate-300 mb-6">
          <Sparkles className="w-4 h-4 text-amber-700 dark:text-amber-400" />
          ATS-optimized · Evidence-based · Never fabricates metrics
        </div>
        <h1 className="text-4xl sm:text-5xl font-bold tracking-tight mb-5 leading-tight">
          Not sure what to apply for?{" "}
          <span className="text-amber-700 dark:text-amber-400">
            Start with what you&rsquo;ve done.
          </span>
        </h1>
        <p className="text-lg sm:text-xl text-slate-600 dark:text-slate-400 mb-3 max-w-2xl mx-auto">
          Tell TalioCV your career story once. It finds the job titles you
          actually fit, then tailors an ATS-optimized resume to every job
          description you paste &mdash; using only your real experience.
        </p>
      </div>

      <div className="mt-8 max-w-4xl mx-auto">
        <ProductScreenshot priority />
      </div>

      <div className="mt-8 text-center">
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link href="/auth?mode=register" className={PRIMARY_CTA}>
            Start your career story
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link href="/checkup" className={SECONDARY_CTA}>
            <FileSearch className="w-4 h-4" />
            Check a resume free
          </Link>
        </div>
        <p className="mt-4 text-slate-600 dark:text-slate-400 text-sm">
          {formatSignupCreditsCopy(startingCredits)} · No credit card required
        </p>
        <p className="mt-1 text-slate-500 dark:text-slate-500 text-xs">
          The resume checkup needs no account at all. Registering takes about a
          minute and includes {startingCredits} AI {creditsLabel}.
        </p>
      </div>
    </section>
  );
}
