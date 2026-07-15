"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Check, ChevronDown, ChevronUp, MessageSquare, Sparkles, X, Zap } from "lucide-react";
import { type BlockingIssue, type IssueAnchor, type QAOutput } from "@/lib/api";
import { cn } from "@/lib/utils";
import { ScoreBreakdownPanel } from "./ScoreBreakdownPanel";

interface Props {
  output: QAOutput | null;
  streaming?: boolean;
  scoreHistory?: number[];
  /** Issue keys greyed out after the user accepted a chat patch for them. */
  addressedKeys?: ReadonlySet<string>;
  /** Issue keys hidden after the user clicked Skip. */
  skippedKeys?: ReadonlySet<string>;
  onSkipIssue?: (issue: BlockingIssue) => void;
  /** Open chat to fix issues; parent tracks targets until a patch is accepted. */
  onSendToChat?: (message: string, issues: BlockingIssue[]) => void;
  /**
   * Called when user clicks "Fix with AI" on a blocking issue (primary/export variant).
   * Receives all blocking issues with the clicked one first so the caller can drive a queue.
   */
  onStartQueue?: (orderedIssues: BlockingIssue[]) => void;
  /** Primary = full-width top section (Phase 4); sidebar = compact collapsible panel (Phase 3). */
  variant?: "primary" | "sidebar";
  /** ISO timestamp when the resume changed after this score was computed. */
  staleSince?: string | null;
  /** Triggers a fresh Phase 4 run. Shown as the "Recalculate" CTA when staleSince is set. */
  onRecalculate?: () => void;
  /** Disables the recalc button while a phase is already in flight. */
  recalculateDisabled?: boolean;
  /** Scroll the tailored editor to an anchored resume entry. */
  onScrollToAnchor?: (anchor: IssueAnchor) => void;
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

const RANK_LABELS = {
  needs_work: "Needs work",
  fair: "Fair",
  good: "Good",
  great: "Great",
  excellent: "Excellent",
} as const;

const RANK_STYLES = {
  needs_work: "bg-red-400/15 text-red-300 border-red-400/30",
  fair: "bg-amber-400/15 text-amber-300 border-amber-400/30",
  good: "bg-emerald-400/15 text-emerald-300 border-emerald-400/30",
  great: "bg-emerald-400/20 text-emerald-200 border-emerald-400/40",
  excellent: "bg-emerald-400/25 text-emerald-100 border-emerald-400/50",
} as const;

const NARRATIVE_SEVERITY_STYLES = {
  minor: "bg-slate-600/30 text-slate-300 border-slate-600",
  urgent: "bg-amber-400/15 text-amber-300 border-amber-400/30",
  critical: "bg-red-400/15 text-red-300 border-red-400/30",
} as const;

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


function QuickWinCard({
  issue,
  addressed = false,
  onSkip,
  onFixWithAI,
}: {
  issue: BlockingIssue;
  addressed?: boolean;
  onSkip: () => void;
  onFixWithAI?: () => void;
}) {
  return (
    <div
      className={cn(
        "border rounded-xl p-3 space-y-2 transition-colors",
        addressed
          ? "bg-slate-800/50 border-slate-600/60 opacity-75"
          : "bg-emerald-400/5 border-emerald-400/20",
      )}
    >
      <div className="flex items-start gap-2">
        <Zap
          className={cn(
            "w-4 h-4 shrink-0 mt-0.5",
            addressed ? "text-slate-500" : "text-emerald-400",
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={cn(
                "text-[10px] uppercase tracking-wide font-semibold",
                addressed ? "text-slate-500" : "text-emerald-400/80",
              )}
            >
              {CATEGORY_LABELS[issue.category]}
            </span>
            {addressed && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-700/80 text-slate-400 border border-slate-600/60">
                Addressed
              </span>
            )}
          </div>
          <p className={cn("text-sm mt-0.5", addressed ? "text-slate-500" : "text-slate-200")}>
            {issue.description}
          </p>
          <p className={cn("text-xs mt-1", addressed ? "text-slate-600" : "text-slate-400")}>
            {issue.suggestion}
          </p>
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {onFixWithAI && (
          <button
            type="button"
            onClick={onFixWithAI}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
              addressed
                ? "bg-slate-700/60 border border-slate-600 text-slate-400 hover:bg-slate-600/60 hover:text-slate-200"
                : "bg-amber-400/10 border border-amber-400/20 text-amber-400 hover:bg-amber-400/20",
            )}
          >
            <MessageSquare className="w-3 h-3" />
            {addressed ? "Fix again" : "Fix with AI"}
          </button>
        )}
        {!addressed && (
          <button
            type="button"
            onClick={onSkip}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-700/60 border border-slate-700 text-slate-400 text-xs font-semibold hover:bg-red-900/30 hover:text-red-400 transition-colors"
          >
            <X className="w-3 h-3" />
            Skip
          </button>
        )}
      </div>
    </div>
  );
}

function BlockingIssueRow({
  issue,
  defaultOpen,
  addressed = false,
  onSendToChat,
  onStartQueue,
  onScrollToAnchor,
  selected,
  onToggleSelect,
}: {
  issue: BlockingIssue;
  defaultOpen?: boolean;
  addressed?: boolean;
  onSendToChat?: () => void;
  onStartQueue?: () => void;
  onScrollToAnchor?: (anchor: IssueAnchor) => void;
  selected?: boolean;
  onToggleSelect?: () => void;
}) {
  const [open, setOpen] = useState(defaultOpen ?? false);

  return (
    <div
      className={cn(
        "border rounded-lg overflow-hidden transition-colors",
        addressed
          ? "border-slate-600/60 bg-slate-800/40 opacity-75"
          : selected
          ? "border-amber-400/50 bg-amber-400/5"
          : "border-slate-700",
      )}
    >
      <div className="flex items-stretch">
        {onToggleSelect && (
          <button
            type="button"
            onClick={onToggleSelect}
            aria-label={selected ? "Deselect issue" : "Select issue for batch fix"}
            className={cn(
              "shrink-0 px-3 flex items-center justify-center border-r transition-colors",
              selected
                ? "bg-amber-400/15 border-amber-400/40"
                : "bg-slate-800/50 border-slate-700 hover:bg-slate-800",
            )}
          >
            <span
              className={cn(
                "w-4 h-4 rounded border flex items-center justify-center",
                selected
                  ? "bg-amber-400 border-amber-400"
                  : "border-slate-500 bg-transparent",
              )}
            >
              {selected && <Check className="w-3 h-3 text-slate-900" />}
            </span>
          </button>
        )}
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex-1 min-w-0 flex items-center gap-2 px-3 py-2.5 bg-slate-800/50 hover:bg-slate-800 text-left transition"
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
        {addressed && (
          <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-700/80 text-slate-400 border border-slate-600/60 shrink-0">
            Addressed
          </span>
        )}
        <span className={cn("text-sm flex-1 truncate", addressed ? "text-slate-500" : "text-slate-300")}>
          {issue.description}
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
        )}
      </button>
      </div>
      {open && (
        <div className="px-3 py-2.5 border-t border-slate-700 bg-slate-900/40 space-y-2">
          <p className="text-slate-400 text-xs">
            <span className="text-slate-500 font-medium">Suggestion: </span>
            {issue.suggestion}
          </p>
          <p className="text-[10px] text-slate-600">
            Fix effort: {issue.fix_effort.replace(/_/g, " ")}
          </p>
          {issue.anchor && onScrollToAnchor && (
            <button
              type="button"
              onClick={() => onScrollToAnchor(issue.anchor!)}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-600 text-slate-300 text-xs font-semibold hover:bg-slate-700 transition-colors"
            >
              Jump to entry →
            </button>
          )}
          {/* Primary variant: queue-based flow */}
          {onStartQueue && (
            <button
              type="button"
              onClick={onStartQueue}
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400/10 border border-amber-400/20 text-amber-400 text-xs font-semibold hover:bg-amber-400/20 transition-colors"
            >
              <MessageSquare className="w-3 h-3" />
              Fix with AI →
            </button>
          )}
          {!onStartQueue && onSendToChat && (
            <button
              type="button"
              onClick={onSendToChat}
              className={cn(
                "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
                addressed
                  ? "bg-slate-700/60 border border-slate-600 text-slate-400 hover:bg-slate-600/60"
                  : "bg-amber-400/10 border border-amber-400/20 text-amber-400 hover:bg-amber-400/20",
              )}
            >
              <MessageSquare className="w-3 h-3" />
              {addressed ? "Fix again →" : "Fix with AI →"}
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

/** Stable key for deduping the same issue across quick_wins and blocking_issues. */
export function issueKey(issue: BlockingIssue): string {
  return `${issue.category}|${issue.description}|${issue.suggestion}`;
}

function buildQuickWinChatMessage(issue: BlockingIssue): string {
  return `Apply this quick win to my resume:\n[${CATEGORY_LABELS[issue.category]}] ${issue.description}\n\nHow to fix: ${issue.suggestion}`;
}

function buildBlockingChatMessage(issue: BlockingIssue): string {
  return `Fix this issue in my resume:\n[${CATEGORY_LABELS[issue.category]}] ${issue.description}\nSuggestion: ${issue.suggestion}\nFix effort: ${issue.fix_effort.replace(/_/g, " ")}`;
}

function buildBatchChatMessage(issues: BlockingIssue[]): string {
  const lines = issues.map(
    (i, n) =>
      `${n + 1}. [${CATEGORY_LABELS[i.category]}] ${i.description}\n   Suggestion: ${i.suggestion}`,
  );
  return `Address these ${issues.length} issues in my resume in a single round of edits:\n\n${lines.join("\n\n")}\n\nReturn patches for as many as you can apply at once.`;
}

export function ATSGuidancePanel({
  output,
  streaming = false,
  scoreHistory = [],
  addressedKeys = new Set<string>(),
  skippedKeys = new Set<string>(),
  onSkipIssue,
  onSendToChat,
  onStartQueue,
  variant = "primary",
  staleSince = null,
  onRecalculate,
  recalculateDisabled = false,
  onScrollToAnchor,
}: Props) {
  const [sidebarOpen, setSidebarOpen] = useState(true);
  const [selectedKeys, setSelectedKeys] = useState<Set<string>>(new Set());

  // Reset selection when the QA output changes (new recalculation).
  const outputRef = useRef(output);
  useEffect(() => {
    if (output !== outputRef.current) {
      outputRef.current = output;
      setSelectedKeys(new Set());
    }
  }, [output]);

  function sendIssuesToChat(issues: BlockingIssue[], message: string) {
    if (issues.length === 0 || !onSendToChat) return;
    onSendToChat(message, issues);
  }

  function toggleBlockingSelection(key: string) {
    setSelectedKeys((prev) => {
      const next = new Set(prev);
      if (next.has(key)) {
        next.delete(key);
      } else {
        next.add(key);
      }
      return next;
    });
  }

  function skipIssue(issue: BlockingIssue) {
    onSkipIssue?.(issue);
  }

  function fixSingleQuickWin(issue: BlockingIssue) {
    sendIssuesToChat([issue], buildQuickWinChatMessage(issue));
  }

  function fixSingleBlockingIssue(issue: BlockingIssue) {
    sendIssuesToChat([issue], buildBlockingChatMessage(issue));
  }

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

  const blocking = sortBlockingIssues(output.blocking_issues ?? []).filter(
    (issue) => !skippedKeys.has(issueKey(issue)),
  );
  const quickWins = (output.quick_wins ?? []).filter(
    (issue) => !skippedKeys.has(issueKey(issue)),
  );
  const addressedCount = [...quickWins, ...blocking].filter((issue) =>
    addressedKeys.has(issueKey(issue)),
  ).length;
  const ringSize = variant === "sidebar" ? 72 : 96;

  const content = (
    <div className={cn("space-y-5", variant === "sidebar" && "text-sm")}>
      {/* Stale banner — shown after the user accepts a chat patch but hasn't recalculated yet */}
      {staleSince && (
        <div className="flex items-center justify-between gap-3 px-3 py-2 rounded-lg bg-amber-400/10 border border-amber-400/30">
          <span className="text-xs text-amber-300">
            Resume changed since this score was computed. The number below may be out of date.
          </span>
          {onRecalculate && (
            <button
              type="button"
              onClick={onRecalculate}
              disabled={recalculateDisabled}
              className="shrink-0 px-2.5 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 disabled:opacity-50 text-amber-200 text-xs font-semibold border border-amber-400/40"
            >
              Recalculate
            </button>
          )}
        </div>
      )}

      {/* Score header */}
      <div className="flex items-center gap-4 flex-wrap">
        <ScoreRing score={output.ats_score} size={ringSize} />
        <div className="flex-1 min-w-0 space-y-1">
          <div className="flex items-center gap-2 flex-wrap">
            <Sparkles className="w-4 h-4 text-amber-400" />
            <h2 className={cn("font-bold text-slate-100", variant === "primary" ? "text-lg" : "text-base")}>
              ATS Score
            </h2>
            {output.rank_label && (
              <span
                className={cn(
                  "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide border",
                  RANK_STYLES[output.rank_label],
                )}
              >
                {RANK_LABELS[output.rank_label]}
              </span>
            )}
          </div>
          {output.headline && (
            <p className="text-sm text-slate-300 leading-relaxed">{output.headline}</p>
          )}
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

      {/* Deterministic per-axis breakdown */}
      {output.score_axes && output.score_axes.length > 0 && (
        <ScoreBreakdownPanel
          axes={output.score_axes}
          defaultOpen={variant === "primary"}
        />
      )}

      {output.category_summaries && output.category_summaries.length > 0 && (
        <section className="space-y-3">
          <h3 className="text-sm font-semibold text-slate-200">Analysis highlights</h3>
          <div className="space-y-2">
            {output.category_summaries.map((category) => (
              <div
                key={category.category_key}
                className="border border-slate-700 rounded-lg bg-slate-900/40 p-3 space-y-2"
              >
                <div className="flex items-center justify-between gap-2 flex-wrap">
                  <span className="text-sm font-medium text-slate-100">{category.label}</span>
                  <div className="flex items-center gap-2">
                    {category.issue_count > 0 && (
                      <span className="text-xs text-slate-400 tabular-nums">
                        {category.issue_count} issue{category.issue_count === 1 ? "" : "s"}
                      </span>
                    )}
                    <span
                      className={cn(
                        "px-1.5 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wide border",
                        NARRATIVE_SEVERITY_STYLES[category.severity],
                      )}
                    >
                      {category.severity}
                    </span>
                  </div>
                </div>
                {category.why_it_matters && (
                  <p className="text-xs text-slate-400 leading-relaxed">{category.why_it_matters}</p>
                )}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* Quick wins */}
      {quickWins.length > 0 && (
        <section>
          <h3 className="text-emerald-400 font-semibold text-sm flex items-center gap-1.5 mb-2">
            <Zap className="w-4 h-4" />
            Quick wins
          </h3>
          <p className="text-[11px] text-slate-500 mb-2">
            Fix with AI opens chat and proposes resume edits — accept each patch on your resume to apply it.
            Items grey out after a patch is accepted. Use Skip if you do not want to fix one.
            {addressedCount > 0 && (
              <span className="text-slate-600"> · {addressedCount} addressed</span>
            )}
          </p>
          <div className="space-y-2">
            {quickWins.map((issue) => {
              const key = issueKey(issue);
              const addressed = addressedKeys.has(key);
              return (
              <QuickWinCard
                key={key}
                issue={issue}
                addressed={addressed}
                onSkip={() => skipIssue(issue)}
                onFixWithAI={onSendToChat ? () => fixSingleQuickWin(issue) : undefined}
              />
            );})}
          </div>
        </section>
      )}

      {/* Blocking issues */}
      {blocking.length > 0 && (
        <section>
          <div className="flex items-center justify-between mb-2 gap-2 flex-wrap">
            <h3 className="text-slate-300 font-semibold text-sm">
              Blocking issues ({blocking.length})
            </h3>
            {(onStartQueue || onSendToChat) && (
              <div className="flex items-center gap-2 text-[11px]">
                {selectedKeys.size > 0 ? (
                  <button
                    type="button"
                    onClick={() => setSelectedKeys(new Set())}
                    className="text-slate-400 hover:text-slate-200"
                  >
                    Clear ({selectedKeys.size})
                  </button>
                ) : (
                  <button
                    type="button"
                    onClick={() => setSelectedKeys(new Set(blocking.map((issue) => issueKey(issue))))}
                    className="text-slate-400 hover:text-slate-200"
                  >
                    Select all
                  </button>
                )}
              </div>
            )}
          </div>

          {/* Batch action toolbar — shown when any issues are selected */}
          {selectedKeys.size > 0 && (() => {
            const selectedIssues = blocking.filter((issue) => selectedKeys.has(issueKey(issue)));
            const hasLength = selectedIssues.some((issue) => issue.category === "length");
            const hasNonLength = selectedIssues.some((issue) => issue.category !== "length");
            const conflicting = hasLength && hasNonLength;
            return (
            <div className="mb-3 p-3 rounded-lg bg-amber-400/10 border border-amber-400/30 flex flex-col gap-2">
              {conflicting && (
                <p className="text-[11px] text-amber-300/80">
                  Length issues can't be fixed while adding content — deselect the Length issue or fix it separately after other edits are done.
                </p>
              )}
              <div className="flex items-center gap-2 flex-wrap">
              <span className="text-xs text-amber-200 font-semibold flex-1 min-w-0">
                {selectedKeys.size} issue{selectedKeys.size === 1 ? "" : "s"} selected
              </span>
              {onStartQueue && (
                <button
                  type="button"
                  onClick={() => {
                    if (selectedIssues.length === 0) return;
                    setSelectedKeys(new Set());
                    onStartQueue(selectedIssues);
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-900 text-xs font-bold transition-colors"
                >
                  <MessageSquare className="w-3 h-3" />
                  Fix one by one
                </button>
              )}
              {onSendToChat && (
                <button
                  type="button"
                  onClick={() => {
                    if (selectedIssues.length === 0) return;
                    sendIssuesToChat(selectedIssues, buildBatchChatMessage(selectedIssues));
                    setSelectedKeys(new Set());
                  }}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-400/15 hover:bg-amber-400/25 border border-amber-400/40 text-amber-200 text-xs font-semibold transition-colors"
                >
                  <MessageSquare className="w-3 h-3" />
                  Fix together
                </button>
              )}
              </div>
            </div>
            );
          })()}

          <div className="space-y-1.5">
            {blocking.map((issue, renderIdx) => {
              const key = issueKey(issue);
              const addressed = addressedKeys.has(key);
              return (
              <BlockingIssueRow
                key={key}
                issue={issue}
                addressed={addressed}
                defaultOpen={renderIdx === 0 && variant === "primary" && selectedKeys.size === 0}
                selected={selectedKeys.has(key)}
                onToggleSelect={
                  (onStartQueue || onSendToChat)
                    ? () => toggleBlockingSelection(key)
                    : undefined
                }
                onSendToChat={onSendToChat ? () => fixSingleBlockingIssue(issue) : undefined}
                onStartQueue={onStartQueue
                  ? () => {
                      const others = blocking.filter((i) => issueKey(i) !== key);
                      onStartQueue([issue, ...others]);
                    }
                  : undefined}
                onScrollToAnchor={onScrollToAnchor}
              />
            );})}
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

/** Exported for component tests and page-level usage. */
export { sortBlockingIssues, scoreColor, CATEGORY_LABELS };
