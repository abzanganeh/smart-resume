"use client";

import { type TailoredResumeOutput, type MetricNeeded } from "@/lib/api";
import { AlertCircle } from "lucide-react";

interface Props {
  original: string;
  tailored: TailoredResumeOutput | null;
  streaming: boolean;
  costInfo?: { cost_formatted: string; provider: string; model: string } | null;
}

function renderTailoredText(output: TailoredResumeOutput): string {
  const lines: string[] = [];
  const c = output.contact as Record<string, string>;
  lines.push(c.name ?? "", c.email ?? "", "");
  if (output.summary) lines.push("SUMMARY", output.summary, "");
  if (output.skills.length) lines.push("SKILLS", output.skills.join(" · "), "");
  if (output.experience.length) {
    lines.push("EXPERIENCE");
    for (const exp of output.experience) {
      lines.push(`${exp.title} | ${exp.company} | ${exp.dates}`);
      for (const b of exp.bullets) lines.push(`  • ${b}`);
      lines.push("");
    }
  }
  return lines.join("\n");
}

export function ResumeDiff({ original, tailored, streaming, costInfo }: Props) {
  if (streaming && !tailored) {
    return (
      <div className="space-y-3">
        {costInfo && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm text-slate-300">
            Estimated cost: <span className="text-amber-400 font-semibold">{costInfo.cost_formatted}</span>
            <span className="text-slate-500 ml-2">({costInfo.provider} · {costInfo.model})</span>
          </div>
        )}
        <div className="flex items-center gap-2 text-slate-400 py-8">
          <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          Rewriting resume sections…
        </div>
      </div>
    );
  }
  if (!tailored) return null;

  const tailoredText = renderTailoredText(tailored);

  return (
    <div className="space-y-4">
      {/* Metrics needed */}
      {tailored.metrics_needed.length > 0 && (
        <div className="bg-amber-400/10 border border-amber-400/30 rounded-xl p-4 space-y-2">
          <div className="flex items-center gap-2 text-amber-400 font-semibold text-sm">
            <AlertCircle className="w-4 h-4" />
            Action required: add metrics to these bullets
          </div>
          {tailored.metrics_needed.map((m: MetricNeeded, i) => (
            <div key={i} className="text-amber-300 text-sm pl-6">
              <span className="opacity-70 text-xs">{m.section}{m.company ? ` · ${m.company}` : ""} · bullet {m.bullet_index + 1}: </span>
              {m.prompt}
            </div>
          ))}
        </div>
      )}

      {/* Side-by-side diff */}
      <div className="grid grid-cols-2 gap-4">
        <div>
          <h3 className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">Original</h3>
          <pre className="bg-slate-900 border border-slate-800 rounded-xl p-4 text-slate-400 text-xs whitespace-pre-wrap leading-relaxed overflow-auto max-h-[600px]">
            {original}
          </pre>
        </div>
        <div>
          <h3 className="text-amber-400 text-xs font-medium uppercase tracking-wider mb-2">Tailored</h3>
          <pre className="bg-slate-900 border border-amber-400/20 rounded-xl p-4 text-slate-200 text-xs whitespace-pre-wrap leading-relaxed overflow-auto max-h-[600px]">
            {tailoredText}
          </pre>
        </div>
      </div>

      {/* Rewrite notes */}
      {tailored.rewrite_notes.length > 0 && (
        <div>
          <h3 className="text-slate-400 text-xs font-medium uppercase tracking-wider mb-2">What changed</h3>
          <ul className="space-y-1">
            {tailored.rewrite_notes.map((note, i) => (
              <li key={i} className="text-slate-400 text-xs flex items-start gap-2">
                <span className="text-amber-400 mt-0.5">›</span>
                {note}
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
