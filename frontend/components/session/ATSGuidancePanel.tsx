"use client";

import { useState } from "react";
import { ChevronDown, ChevronUp, Sparkles, Zap } from "lucide-react";
import { type BlockingIssue, type QAOutput } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: QAOutput | null;
  streaming?: boolean;
  scoreHistory?: number[];
  onApplySuggestion?: (suggestion: string) => void;
  /** Primary = full-width top section (Phase 4); sidebar = compact collapsible panel (Phase 3). */
  variant?: "primary" | "sidebar";
}

const IMPACT_ORDER = { high: 0, medium: 1, low: 2 } as const;
const EFFORT_ORDER = { one_click: 0, user_input: 1, manual_rewrite: 2 } as const;

const CATEGORY_LABELS: Record<BlockingIssue["category"], string> = {
  keyword: "Keyword",
  bullet: "Bullet",
  metric: "Metric",
  format: "Format",
  length: "Length",
  section: "Section",
};

const IMPACT_STYLES: Record<BlockingIssue["impact"], string> = {
  high: "bg-red-400/15 text-red-300 border-red-400/30",
  medium: "bg-amber-400/15 text-amber-300 border-amber-400/30",
  low: "bg-slate-600/40 text-slate-400 border-slate-600",
};

function scoreColor(score: number): string {
  if (score >= 70) return "text-green-400";
  if (score >= 45) return "text-amber-400";
  return "text-red-400";
}

function ScoreRing({ score, size = 96 }: { score: number; size?: number }) {
  const stroke = 6;
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;
  const color =
    score >= 70 ? "#4ade80" : score >= 45 ? "#fbbf24" : "#f87171";

  return (
    <div className="relative shrink-0" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="currentColor"
          strokeWidth={stroke}
          className="text-slate-700"
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={stroke}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          className="transition-all duration-700"
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={cn("text-2xl font-bold tabular-nums", scoreColor(score))}>
          {score}
        </span>
        <span className="text-[10px] text-slate-500 uppercase tracking-wide">/ 100</span>
      </div>
    </div>
  );
}

function TrendSparkline({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;

  const w = 120;
  const h = 32;
  const pad = 4;
  const min = Math.min(...scores, 0);
  const max = Math.max(...scores, 100);
  const range = max - min || 1;

  const points = scores
    .map((s, i) => {
      const x = pad + (i / (scores.length - 1)) * (w - pad * 2);
      const y = h - pad - ((s - min) / range) * (h - pad * 2);
      return `${x},${y}`;
    })
    .join(" ");

  const latest = scores[scores.length - 1];
  const prev = scores[scores.length - 2];
  const trendUp = latest >= prev;

  return (
    <div className="flex items-center gap-2">
      <svg width={w} height={h} className="overflow-visible">
        <polyline
          points={points}
          fill="none"
          stroke={trendUp ? "#4ade80" : "#f87171"}
          strokeWidth={2}
          strokeLinecap="round"
          strokeLinejoin="round"
        />
        {scores.map((s, i) => {
          const x = pad + (i / (scores.length - 1)) * (w - pad * 2);
          const y = h - pad - ((s - min) / range) * (h - pad * 2);
          return (
            <circle
              key={i}
              cx={x}
              cy={y}
              r={3}
              fill={i === scores.length - 1 ? (trendUp ? "#4ade80" : "#f87171") : "#64748b"}
            />
          );
        })}
      </svg>
      <span className="text-[10px] text-slate-500">Last {scores.length} runs</span>
    </div>
  );
}

function QuickWinCard({
  issue,
  onApply,
}: {
  issue: BlockingIssue;
  onApply?: (suggestion: string) => void;
}) {
  return (
    <div className="bg-emerald-400/5 border border-emerald-400/20 rounded-xl p-3 space-y-2">
      <div className="flex items-start gap-2">
        <Zap className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <span className="text-[10px] uppercase tracking-wide text-emerald-400/80 font-semibold">
            {CATEGORY_LABELS[issue.category]}
          </span>
          <p className="text-slate-200 text-sm mt-0.5">{issue.description}</p>
          <p className="text-slate-400 text-xs mt-1">{issue.suggestion}</p>
        </div>
      </div>
      {onApply && (
        <button
          type="button"
          onClick={() => onApply(issue.suggestion)}
          className="w-full px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors"
        >
          Apply
        </button>
      )}
    </div>
  );
}

function BlockingIssueRow({ issue, defaultOpen }: { issue: BlockingIssue; defaultOpen?: boolean }) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div className="border border-slate-700 rounded-lg overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-2 px-3 py-2.5 bg-slate-800/50 hover:bg-slate-800 text-left transition"
      >
        <span
          className={cn(
            "text-[10px] uppercase tracking-wide font-semibold px-1.5 py-0.5 rounded border shrink-0",
            IMPACT_STYLES[issue.impact],
          )}
        >
          {issue.impact}
        </span>
        <span className="text-[10px] text-slate-500 uppercase shrink-0">
          {CATEGORY_LABELS[issue.category]}
        </span>
        <span className="text-slate-300 text-sm flex-1 truncate">{issue.description}</span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
        )}
      </button>
      {open && (
        <div className="px-3 py-2.5 border-t border-slate-700 bg-slate-900/40 space-y-1">
          <p className="text-slate-400 text-xs">
            <span className="text-slate-500 font-medium">Suggestion: </span>
            {issue.suggestion}
          </p>
          <p className="text-[10px] text-slate-600">
            Fix effort: {issue.fix_effort.replace(/_/g, " ")}
          </p>
        </div>
      )}
    </div>
  );
}

function sortBlockingIssues(issues: BlockingIssue[]): BlockingIssue[] {
  return [...issues].sort((a, b) => {
    const impactDiff = IMPACT_ORDER[a.impact] - IMPACT_ORDER[b.impact];
    if (impactDiff !== 0) return impactDiff;
    return EFFORT_ORDER[a.fix_effort] - EFFORT_ORDER[b.fix_effort];
  });
}

export function ATSGuidancePanel({
  output,
  streaming = false,
  scoreHistory = [],
  onApplySuggestion,
  variant = "primary",
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(true);

  if (streaming && !output) {
    return (
      <div className="flex items-center gap-2 text-slate-400 py-6">
        <div className="w-5 h-5 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        Calculating ATS score…
      </div>
    );
  }

  if (!output || output.ats_score === undefined) {
    return (
      <div className="text-slate-500 text-sm py-4">
        Run QA or recalculate to see ATS guidance.
      </div>
    );
  }

  const blocking = sortBlockingIssues(output.blocking_issues ?? []);
  const quickWins = output.quick_wins ?? [];
  const ringSize = variant === "sidebar" ? 72 : 96;

  const content = (
    <div className={cn("space-y-5", variant === "sidebar" && "text-sm")}>
      {/* Score header */}
      <div className="flex items-center gap-4 flex-wrap">
        <ScoreRing score={output.ats_score} size={ringSize} />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <h2 className={cn("font-bold text-slate-100", variant === "primary" ? "text-lg" : "text-base")}>
              ATS Score
            </h2>
          </div>
          <p className="text-slate-400 text-sm">
            Up to <span className="text-amber-400 font-semibold">{output.score_ceiling}</span> achievable
            with current master resume
          </p>
          {scoreHistory.length >= 2 && (
            <TrendSparkline scores={scoreHistory} />
          )}
        </div>
      </div>

      {/* Quick wins */}
      {quickWins.length > 0 && (
        <section>
          <h3 className="text-emerald-400 font-semibold text-sm mb-2 flex items-center gap-1.5">
            <Zap className="w-4 h-4" />
            Quick wins
          </h3>
          <div className="space-y-2">
            {quickWins.map((issue, i) => (
              <QuickWinCard key={i} issue={issue} onApply={onApplySuggestion} />
            ))}
          </div>
        </section>
      )}

      {/* Blocking issues */}
      {blocking.length > 0 && (
        <section>
          <h3 className="text-slate-300 font-semibold text-sm mb-2">
            Blocking issues ({blocking.length})
          </h3>
          <div className="space-y-1.5">
            {blocking.map((issue, i) => (
              <BlockingIssueRow key={i} issue={issue} defaultOpen={i === 0 && variant === "primary"} />
            ))}
          </div>
        </section>
      )}
    </div>
  );

  if (variant === "sidebar") {
    return (
      <aside className="border border-slate-700 rounded-xl bg-slate-900/60 overflow-hidden">
        <button
          type="button"
          onClick={() => setSidebarOpen((v) => !v)}
          className="w-full flex items-center justify-between px-4 py-3 bg-slate-800/60 hover:bg-slate-800 text-left"
        >
          <span className="text-sm font-semibold text-slate-200 flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-amber-400" />
            ATS Guidance
            <span className={cn("tabular-nums", scoreColor(output.ats_score))}>
              {output.ats_score}/100
            </span>
          </span>
          {sidebarOpen ? (
            <ChevronUp className="w-4 h-4 text-slate-500" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-500" />
          )}
        </button>
        {sidebarOpen && <div className="p-4">{content}</div>}
      </aside>
    );
  }

  return content;
}

/** Exported for component tests — mirrors panel sort order. */
export { sortBlockingIssues, scoreColor };
