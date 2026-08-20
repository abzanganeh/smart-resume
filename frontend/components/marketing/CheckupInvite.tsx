import Link from "next/link";
import { ArrowRight, FileSearch } from "lucide-react";
import { PRIMARY_CTA } from "./styles";

/**
 * Drives visitors into `/checkup` — the real, unauthenticated ATS analyzer —
 * rather than showing a mocked score comparison.
 */
export function CheckupInvite() {
  return (
    <section className="max-w-3xl mx-auto px-6 pb-24">
      <div className="rounded-2xl border border-amber-400/40 bg-amber-500/5 dark:bg-amber-400/5 p-8 text-center">
        <FileSearch className="w-6 h-6 mx-auto text-amber-700 dark:text-amber-400 mb-4" />
        <h2 className="text-2xl font-semibold mb-3 text-slate-900 dark:text-slate-100">
          See it on your own resume first
        </h2>
        <p className="text-slate-600 dark:text-slate-400 text-sm leading-relaxed max-w-xl mx-auto mb-6">
          Paste a resume and a job description and get the real ATS-style score,
          the issues behind it, and the quick wins that would close the gap. No
          account, no paywall, no sample data &mdash; the same analysis
          registered users get.
        </p>
        <Link href="/checkup" className={PRIMARY_CTA}>
          Run a free resume checkup
          <ArrowRight className="w-5 h-5" />
        </Link>
      </div>
    </section>
  );
}
