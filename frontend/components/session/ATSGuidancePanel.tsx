"use client";

import { useState } from "react";
import { Check, ChevronDown, ChevronUp, MessageSquare, Sparkles, X, Zap } from "lucide-react";
import { type BlockingIssue, type QAOutput } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: QAOutput | null;
  streaming?: boolean;
  scoreHistory?: number[];
  onApplySuggestion?: (suggestion: string) => void;
  /** Called when user wants to send a suggestion directly to the chat. */
  onSendToChat?: (message: string) => void;
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

function ScoreHistory({ scores }: { scores: number[] }) {
  if (scores.length < 2) return null;

  const baseline = scores[0];
  const latest = scores[scores.length - 1];
  const delta = latest - baseline;
  const trendUp = delta > 0;
  const unchanged = delta === 0;

  // Mini sparkline
  const w = 80;
  const h = 24;
  const pad = 3;
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

  const lineColor = trendUp ? "#4ade80" : unchanged ? "#64748b" : "#f87171";

  return (
    <div className="space-y-1.5">
      {/* Baseline → current comparison */}
      <div className="flex items-center gap-2 flex-wrap">
        <div className="flex items-center gap-1.5 text-[11px]">
          <span className="text-slate-500">Baseline</span>
          <span className="font-bold tabular-nums text-slate-400">{baseline}</span>
          <span className="text-slate-600">→</span>
          <span className="font-bold tabular-nums text-slate-200">Now {latest}</span>
        </div>
        {!unchanged && (
          <span
            className={cn(
              "text-[11px] font-bold tabular-nums px-1.5 py-0.5 rounded",
              trendUp
                ? "bg-emerald-400/15 text-emerald-400"
                : "bg-red-400/15 text-red-400",
            )}
          >
            {trendUp ? "↑" : "↓"} {trendUp ? "+" : ""}{delta} pts
          </span>
        )}
        {unchanged && (
          <span className="text-[11px] text-slate-600 bg-slate-700/40 px-1.5 py-0.5 rounded">
            no change
          </span>
        )}
      </div>

      {/* Mini sparkline + run count */}
      <div className="flex items-center gap-2">
        <svg width={w} height={h} className="overflow-visible shrink-0">
          <polyline
            points={points}
            fill="none"
            stroke={lineColor}
            strokeWidth={1.5}
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
                r={2.5}
                fill={i === scores.length - 1 ? lineColor : "#475569"}
              />
            );
          })}
        </svg>
        <span className="text-[10px] text-slate-600">{scores.length} recalculations</span>
      </div>
    </div>
  );
}

type WinState = "neutral" | "accepted" | "declined";

function QuickWinCard({
  issue,
  state,
  onAccept,
  onDecline,
  onSendToChat,
}: {
  issue: BlockingIssue;
  state: WinState;
  onAccept: () => void;
  onDecline: () => void;
  onSendToChat?: (message: string) => void;
}) {
  const isAccepted = state === "accepted";
  const isDeclined = state === "declined";

  function buildChatMessage() {
    return `Apply this quick win to my resume:\n[${CATEGORY_LABELS[issue.category]}] ${issue.description}\n\nHow to fix: ${issue.suggestion}`;
  }

  return (
    <div
      className={cn(
        "border rounded-xl p-3 space-y-2 transition-colors",
        isAccepted
          ? "bg-emerald-400/10 border-emerald-400/40"
          : isDeclined
          ? "bg-slate-800/30 border-slate-700/40 opacity-50"
          : "bg-emerald-400/5 border-emerald-400/20",
      )}
    >
      <div className="flex items-start gap-2">
        <Zap
          className={cn(
            "w-4 h-4 shrink-0 mt-0.5",
            isAccepted ? "text-emerald-400" : isDeclined ? "text-slate-600" : "text-emerald-400",
          )}
        />
        <div className="flex-1 min-w-0">
          <span className="text-[10px] uppercase tracking-wide text-emerald-400/80 font-semibold">
            {CATEGORY_LABELS[issue.category]}
          </span>
          <p className={cn("text-sm mt-0.5", isDeclined ? "text-slate-500 line-through" : "text-slate-200")}>
            {issue.description}
          </p>
          <p className="text-slate-400 text-xs mt-1">{issue.suggestion}</p>
        </div>
      </div>

      {/* Accept / Decline / Fix with AI */}
      <div className="flex gap-2 flex-wrap">
        <button
          type="button"
          onClick={onAccept}
          className={cn(
            "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
            isAccepted
              ? "bg-emerald-500 text-white"
              : "bg-slate-700/60 text-slate-300 hover:bg-emerald-600/40 hover:text-emerald-300",
          )}
        >
          <Check className="w-3 h-3" />
          {isAccepted ? "Accepted" : "Accept"}
        </button>
        <button
          type="button"
          onClick={onDecline}
          className={cn(
            "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
            isDeclined
              ? "bg-slate-600 text-slate-400"
              : "bg-slate-700/60 text-slate-300 hover:bg-red-900/30 hover:text-red-400",
          )}
        >
          <X className="w-3 h-3" />
          {isDeclined ? "Skipped" : "Skip"}
        </button>
        {onSendToChat && (
          <button
            type="button"
            onClick={() => onSendToChat(buildChatMessage())}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400/10 border border-amber-400/20 text-amber-400 text-xs font-semibold hover:bg-amber-400/20 transition-colors"
          >
            <MessageSquare className="w-3 h-3" />
            Fix with AI
          </button>
        )}
      </div>
    </div>
  );
}

function BlockingIssueRow({
  issue,
  defaultOpen,
  onSendToChat,
}: {
  issue: BlockingIssue;
  defaultOpen?: boolean;
  onSendToChat?: (message: string) => void;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  function buildChatMessage() {
    return `Fix this issue in my resume:\n[${CATEGORY_LABELS[issue.category]}] ${issue.description}\n\nSuggestion: ${issue.suggestion}`;
  }

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
        <div className="px-3 py-2.5 border-t border-slate-700 bg-slate-900/40 space-y-2">
          <p className="text-slate-400 text-xs">
            <span className="text-slate-500 font-medium">Suggestion: </span>
            {issue.suggestion}
          </p>
          <p className="text-[10px] text-slate-600">
            Fix effort: {issue.fix_effort.replace(/_/g, " ")}
          </p>
          {onSendToChat && (
            <button
              type="button"
              onClick={() => onSendToChat(buildChatMessage())}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400/10 border border-amber-400/20 text-amber-400 text-xs font-semibold hover:bg-amber-400/20 transition-colors"
            >
              <MessageSquare className="w-3 h-3" />
              Fix with AI →
            </button>
          )}
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
  onSendToChat,
  variant = "primary",
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [winStates, setWinStates] = useState<Record<number, WinState>>({});

  function setWinState(idx: number, next: WinState) {
    setWinStates((prev) => ({
      ...prev,
      [idx]: prev[idx] === next ? "neutral" : next,
    }));
  }

  function applyAccepted() {
    const quickWins = output?.quick_wins ?? [];
    const accepted = quickWins
      .filter((_, i) => winStates[i] === "accepted")
      .map((issue) => `• [${CATEGORY_LABELS[issue.category]}] ${issue.suggestion}`);
    if (accepted.length > 0) {
      onApplySuggestion?.(accepted.join("\n"));
    }
    setWinStates({});
  }

  const acceptedCount = Object.values(winStates).filter((s) => s === "accepted").length;

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
          <div className="flex items-center gap-1.5 text-sm">
            <span className="text-slate-400">Ceiling</span>
            <span className="text-amber-400 font-semibold">{output.score_ceiling ?? "—"}/100</span>
            {(output.score_ceiling ?? 0) > 0 && (
              <span className="text-slate-600 text-xs">
                ({(output.score_ceiling ?? 0) - output.ats_score > 0
                  ? `${(output.score_ceiling ?? 0) - output.ats_score} pts gap`
                  : "at ceiling"})
              </span>
            )}
          </div>
          {scoreHistory.length >= 2 && (
            <ScoreHistory scores={scoreHistory} />
          )}
        </div>
      </div>

      {/* Quick wins */}
      {quickWins.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-2">
            <h3 className="text-emerald-400 font-semibold text-sm flex items-center gap-1.5">
              <Zap className="w-4 h-4" />
              Quick wins
            </h3>
            {acceptedCount > 0 && (
              <button
                type="button"
                onClick={applyAccepted}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors"
              >
                <Check className="w-3 h-3" />
                Apply {acceptedCount} selected
              </button>
            )}
          </div>
          <p className="text-[11px] text-slate-500 mb-2">
            Accept the wins you want, then click &ldquo;Apply selected&rdquo; to add them to your resume.
          </p>
          <div className="space-y-2">
            {quickWins.map((issue, i) => (
              <QuickWinCard
                key={i}
                issue={issue}
                state={winStates[i] ?? "neutral"}
                onAccept={() => setWinState(i, "accepted")}
                onDecline={() => setWinState(i, "declined")}
                onSendToChat={onSendToChat}
              />
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
              <BlockingIssueRow
                key={i}
                issue={issue}
                defaultOpen={i === 0 && variant === "primary"}
                onSendToChat={onSendToChat}
              />
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
