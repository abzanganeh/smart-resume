"use client";

import { CheckCircle, Info, XCircle } from "lucide-react";
import { type KeywordExtractionOutput, type Keyword } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: KeywordExtractionOutput | null;
  streaming: boolean;
  /** Claimed keywords saved by the user in AuditPanel — used to recompute coverage. */
  claimedKeywords?: string[];
}

const TIER_CONFIG = {
  must_have: { label: "Must-Have", dot: "bg-red-500", badge: "bg-red-500/10 border-red-500/30 text-red-300" },
  nice_to_have: { label: "Nice-to-Have", dot: "bg-amber-400", badge: "bg-amber-500/10 dark:bg-amber-400/10 border-amber-400/30 text-amber-700 dark:text-amber-300" },
};

function KeywordCard({ kw }: { kw: Keyword }) {
  const cfg = TIER_CONFIG[kw.tier];
  return (
    <div className={cn("border rounded-lg p-3 text-sm", cfg.badge)}>
      <div className="flex items-start justify-between gap-2">
        <div>
          <p className="font-semibold">{kw.term}</p>
          <p className="text-xs opacity-70 mt-0.5 line-clamp-2">{kw.source_sentence}</p>
        </div>
        <span title={kw.present_in_resume ? "Already in your resume" : "Missing from your resume"}>
          {kw.present_in_resume ? (
            <CheckCircle className="w-4 h-4 text-green-700 dark:text-green-400 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-4 h-4 text-red-700 dark:text-red-400 shrink-0 mt-0.5" />
          )}
        </span>
      </div>
      <p className="text-xs opacity-60 mt-1.5 italic">{kw.reason}</p>
    </div>
  );
}

export function KeywordDashboard({ output, streaming, claimedKeywords = [] }: Props) {
  if (!output && streaming) {
    return (
      <div className="flex items-center gap-2 text-slate-600 dark:text-slate-400 py-8">
        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        Extracting keywords from job description…
      </div>
    );
  }

  if (!output) return null;

  // Build a normalised set of claimed keywords for fast lookup.
  const claimedSet = new Set(claimedKeywords.map((k) => k.toLowerCase()));

  const mustHavePresent = output.must_have_keywords.filter((k) => k.present_in_resume).length;
  const mustHaveTotal = output.must_have_keywords.length;

  // Recompute coverage to include claimed keywords so the bar updates in real time.
  const claimedBoost = output.must_have_keywords.filter(
    (k) => !k.present_in_resume && claimedSet.has(k.term.toLowerCase())
  ).length;
  const effectivePresent = mustHavePresent + claimedBoost;
  const coveragePct = mustHaveTotal > 0 ? Math.round((mustHavePresent / mustHaveTotal) * 100) : 0;
  const claimedPct = mustHaveTotal > 0 ? Math.round((claimedBoost / mustHaveTotal) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Coverage bar */}
      <div className="bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-slate-700 dark:text-slate-300 text-sm font-medium flex items-center gap-1.5">
            Keyword match in original resume
            <span
              title="This shows how many must-have keywords appear in your uploaded resume. Your ATS score (shown after rewrite) measures the tailored version."
              className="cursor-help text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300"
            >
              <Info className="w-3.5 h-3.5" />
            </span>
          </span>
          <span className="text-amber-700 dark:text-amber-400 font-bold">{effectivePresent} / {mustHaveTotal}</span>
        </div>
        {/* Stacked bar: original match + claimed boost */}
        <div className="h-2 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden flex">
          <div
            className="h-full bg-amber-400 transition-all duration-500"
            style={{ width: `${coveragePct}%` }}
          />
          {claimedBoost > 0 && (
            <div
              className="h-full bg-amber-500/40 dark:bg-amber-400/40 border border-amber-400/60 transition-all duration-500"
              style={{ width: `${claimedPct}%` }}
              title={`+${claimedBoost} keyword${claimedBoost > 1 ? "s" : ""} you claimed — included after rewrite`}
            />
          )}
        </div>
        {claimedBoost > 0 && (
          <p className="text-amber-700 dark:text-amber-400/70 text-xs mt-1">
            +{claimedBoost} claimed keyword{claimedBoost > 1 ? "s" : ""} (outlined) will be incorporated in the rewrite
          </p>
        )}
        <p className="text-slate-600 dark:text-slate-400 text-xs mt-1.5">
          {mustHaveTotal === 0
            ? "No must-have keywords were extracted — use Retry or try a stronger model."
            : mustHaveTotal - effectivePresent > 0
            ? `${mustHaveTotal - effectivePresent} must-have keyword${mustHaveTotal - effectivePresent > 1 ? "s" : ""} will be added by the rewrite.`
            : "All must-have keywords are already covered."}
        </p>
      </div>

      {/* Must-have */}
      {output.must_have_keywords.length > 0 && (
        <div>
          <h3 className="text-slate-800 dark:text-slate-200 font-semibold mb-3 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-red-500 inline-block" />
            Must-Have Keywords ({output.must_have_keywords.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {output.must_have_keywords.map((kw, i) => <KeywordCard key={i} kw={kw} />)}
          </div>
        </div>
      )}

      {/* Nice-to-have */}
      {output.nice_to_have_keywords.length > 0 && (
        <div>
          <h3 className="text-slate-800 dark:text-slate-200 font-semibold mb-3 flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-amber-400 inline-block" />
            Nice-to-Have Keywords ({output.nice_to_have_keywords.length})
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
            {output.nice_to_have_keywords.map((kw, i) => <KeywordCard key={i} kw={kw} />)}
          </div>
        </div>
      )}

      {/* Action verbs + seniority signals */}
      <div className="grid grid-cols-2 gap-4">
        {output.action_verbs.length > 0 && (
          <div>
            <h4 className="text-slate-600 dark:text-slate-400 text-xs font-medium mb-2 uppercase tracking-wider">Role Action Verbs</h4>
            <div className="flex flex-wrap gap-1.5">
              {output.action_verbs.map((v, i) => (
                <span key={i} className="bg-blue-500/10 border border-blue-500/30 text-blue-700 dark:text-blue-300 rounded px-2 py-0.5 text-xs">{v}</span>
              ))}
            </div>
          </div>
        )}
        {output.seniority_signals.length > 0 && (
          <div>
            <h4 className="text-slate-600 dark:text-slate-400 text-xs font-medium mb-2 uppercase tracking-wider">Seniority Signals</h4>
            <div className="flex flex-wrap gap-1.5">
              {output.seniority_signals.map((s, i) => (
                <span key={i} className="bg-purple-500/10 border border-purple-500/30 text-purple-700 dark:text-purple-300 rounded px-2 py-0.5 text-xs">{s}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
