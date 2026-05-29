"use client";

import { CheckCircle, XCircle } from "lucide-react";
import { type KeywordExtractionOutput, type Keyword } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: KeywordExtractionOutput | null;
  streaming: boolean;
}

const TIER_CONFIG = {
  must_have: { label: "Must-Have", dot: "bg-red-500", badge: "bg-red-500/10 border-red-500/30 text-red-300" },
  nice_to_have: { label: "Nice-to-Have", dot: "bg-amber-400", badge: "bg-amber-400/10 border-amber-400/30 text-amber-300" },
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
            <CheckCircle className="w-4 h-4 text-green-400 shrink-0 mt-0.5" />
          ) : (
            <XCircle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
          )}
        </span>
      </div>
      <p className="text-xs opacity-60 mt-1.5 italic">{kw.reason}</p>
    </div>
  );
}

export function KeywordDashboard({ output, streaming }: Props) {
  if (!output && streaming) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-8">
        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        Extracting keywords from job description…
      </div>
    );
  }

  if (!output) return null;

  const mustHavePresent = output.must_have_keywords.filter((k) => k.present_in_resume).length;
  const mustHaveTotal = output.must_have_keywords.length;
  const coveragePct = mustHaveTotal > 0 ? Math.round((mustHavePresent / mustHaveTotal) * 100) : 0;

  return (
    <div className="space-y-6">
      {/* Coverage bar */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
        <div className="flex items-center justify-between mb-2">
          <span className="text-slate-300 text-sm font-medium">Must-have keyword coverage</span>
          <span className="text-amber-400 font-bold">{mustHavePresent} / {mustHaveTotal}</span>
        </div>
        <div className="h-2 bg-slate-700 rounded-full overflow-hidden">
          <div
            className="h-full bg-amber-400 rounded-full transition-all duration-500"
            style={{ width: `${coveragePct}%` }}
          />
        </div>
        <p className="text-slate-500 text-xs mt-1.5">
          {mustHaveTotal === 0
            ? "No must-have keywords were extracted — use Retry or try a stronger model."
            : mustHaveTotal - mustHavePresent > 0
            ? `${mustHaveTotal - mustHavePresent} must-have keyword${mustHaveTotal - mustHavePresent > 1 ? "s" : ""} will be added by the rewrite.`
            : "All must-have keywords are already in your resume."}
        </p>
      </div>

      {/* Must-have */}
      {output.must_have_keywords.length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-3 flex items-center gap-2">
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
          <h3 className="text-slate-200 font-semibold mb-3 flex items-center gap-2">
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
            <h4 className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wider">Role Action Verbs</h4>
            <div className="flex flex-wrap gap-1.5">
              {output.action_verbs.map((v, i) => (
                <span key={i} className="bg-blue-500/10 border border-blue-500/30 text-blue-300 rounded px-2 py-0.5 text-xs">{v}</span>
              ))}
            </div>
          </div>
        )}
        {output.seniority_signals.length > 0 && (
          <div>
            <h4 className="text-slate-400 text-xs font-medium mb-2 uppercase tracking-wider">Seniority Signals</h4>
            <div className="flex flex-wrap gap-1.5">
              {output.seniority_signals.map((s, i) => (
                <span key={i} className="bg-purple-500/10 border border-purple-500/30 text-purple-300 rounded px-2 py-0.5 text-xs">{s}</span>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
