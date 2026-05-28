"use client";

import { AlertTriangle, AlertCircle, Info } from "lucide-react";
import { type AuditOutput } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: AuditOutput | null;
  streaming: boolean;
}

const SEVERITY_CONFIG = {
  high: { icon: AlertCircle, cls: "text-red-400 bg-red-400/10 border-red-400/20" },
  medium: { icon: AlertTriangle, cls: "text-amber-400 bg-amber-400/10 border-amber-400/20" },
  low: { icon: Info, cls: "text-blue-400 bg-blue-400/10 border-blue-400/20" },
};

export function AuditPanel({ output, streaming }: Props) {
  if (!output && streaming) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-8">
        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        Auditing resume against job description…
      </div>
    );
  }
  if (!output) return null;

  const scoreColor = output.overall_score >= 70 ? "text-green-400" : output.overall_score >= 45 ? "text-amber-400" : "text-red-400";

  return (
    <div className="space-y-6">
      {/* Score */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p className="text-slate-400 text-sm">ATS Readiness Score</p>
          <p className={cn("text-3xl font-bold mt-0.5", scoreColor)}>{output.overall_score} <span className="text-slate-500 text-lg font-normal">/ 100</span></p>
        </div>
        <div className="text-right text-sm text-slate-400">
          <p>{output.page_estimate}</p>
          {output.page_limit_exceeded && <p className="text-red-400 text-xs mt-0.5">Page limit exceeded</p>}
        </div>
      </div>

      {/* Summary */}
      {output.summary && (
        <p className="text-slate-300 text-sm bg-slate-800 border border-slate-700 rounded-lg p-3">{output.summary}</p>
      )}

      {/* Missing must-have keywords */}
      {output.keyword_coverage.missing_must_have.length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-2 text-sm">Missing Must-Have Keywords</h3>
          <div className="flex flex-wrap gap-1.5">
            {output.keyword_coverage.missing_must_have.map((kw, i) => (
              <span key={i} className="bg-red-500/10 border border-red-500/30 text-red-300 rounded px-2 py-1 text-xs">{kw}</span>
            ))}
          </div>
        </div>
      )}

      {/* Bullet issues */}
      {output.bullet_issues.length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-3 text-sm">Bullet Issues ({output.bullet_issues.length})</h3>
          <div className="space-y-2">
            {output.bullet_issues.map((issue, i) => {
              const cfg = SEVERITY_CONFIG[issue.severity];
              const Icon = cfg.icon;
              return (
                <div key={i} className={cn("border rounded-lg p-3 text-sm", cfg.cls)}>
                  <div className="flex items-start gap-2">
                    <Icon className="w-4 h-4 shrink-0 mt-0.5" />
                    <div>
                      <p className="font-medium text-xs opacity-70 mb-0.5">
                        {issue.section}{issue.company ? ` · ${issue.company}` : ""} · bullet {issue.bullet_index + 1}
                      </p>
                      <p className="opacity-90">"{issue.original}"</p>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {issue.issues.map((iss, j) => (
                          <span key={j} className="text-xs bg-black/20 rounded px-1.5 py-0.5">{iss.replace(/_/g, " ")}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {/* Clichés */}
      {output.cliches_found.length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-2 text-sm">Clichés to Remove</h3>
          <div className="flex flex-wrap gap-1.5">
            {output.cliches_found.map((c, i) => (
              <span key={i} className="bg-amber-400/10 border border-amber-400/30 text-amber-300 rounded px-2 py-0.5 text-xs line-through">{c}</span>
            ))}
          </div>
        </div>
      )}

      {/* Contact issues */}
      {output.contact_issues.length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-2 text-sm">Contact Issues</h3>
          {output.contact_issues.map((c, i) => (
            <p key={i} className="text-red-400 text-sm">{c}</p>
          ))}
        </div>
      )}
    </div>
  );
}
