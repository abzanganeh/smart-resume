import Link from "next/link";
import { ArrowRight } from "lucide-react";
import { PRIMARY_CTA } from "./styles";

export function ClosingCta({ startingCredits }: { startingCredits: number }) {
  const creditsLabel = startingCredits === 1 ? "credit" : "credits";

  return (
    <section className="text-center pb-24 px-6">
      <h2 className="text-2xl font-semibold mb-3 text-slate-900 dark:text-slate-100">
        From &ldquo;I don&rsquo;t know where to start&rdquo; to applied.
      </h2>
      <p className="text-slate-600 dark:text-slate-400 text-sm mb-8 max-w-md mx-auto">
        Create your free account and get {startingCredits} {creditsLabel} to
        build your master resume and tailor your first application. No credit
        card, no commitment.
      </p>
      <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
        <Link href="/auth?mode=register" className={PRIMARY_CTA}>
          Start my job search
          <ArrowRight className="w-5 h-5" />
        </Link>
        <Link
          href="/auth"
          className="text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 text-sm font-medium transition-colors"
        >
          Already have an account? Sign in
        </Link>
      </div>
    </section>
  );
}
