"use client";

import { Check, MessageSquare, X, Zap } from "lucide-react";
import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";
import {
  previewMechanicalQuickWin,
  type MechanicalFixPreview,
  type MechanicalFixResult,
} from "@/lib/mechanicalFix";
import { cn } from "@/lib/utils";

const CATEGORY_LABELS: Record<BlockingIssue["category"], string> = {
  keyword: "Keyword",
  bullet: "Bullet",
  metric: "Metric",
  format: "Format",
  length: "Length",
  section: "Section",
};

export function formatMechanicalPreviewLine(
  preview: MechanicalFixPreview | null,
): string | null {
  if (!preview || preview.changes.length === 0) return null;
  return preview.changes.map((change) => change.label).join(", ");
}

export function shouldShowWillChangeLine(
  willChange: string | null,
  addressed: boolean,
): boolean {
  return Boolean(willChange) && !addressed;
}

export function shouldShowEmployerConstraintCopy(
  addressed: boolean,
  hasOutcome: boolean,
): boolean {
  return !addressed && !hasOutcome;
}

export type QuickWinMechanicalOutcome =
  | { status: "applied"; changes: string[] }
  | { status: "partial"; changes: string[]; unmet: string[] }
  | { status: "failed"; reason: string };

export function mechanicalOutcomeFromResult(
  result: MechanicalFixResult | null,
): QuickWinMechanicalOutcome {
  if (!result) {
    return {
      status: "failed",
      reason: "Couldn't apply automatically — no matching edit for this item.",
    };
  }
  if (result.changes.length === 0) {
    return {
      status: "failed",
      reason: `Couldn't apply automatically — ${result.unmet.join(", ")}`,
    };
  }
  const changeLabels = result.changes.map((change) => change.label);
  if (result.unmet.length > 0) {
    return { status: "partial", changes: changeLabels, unmet: result.unmet };
  }
  return { status: "applied", changes: changeLabels };
}

export function shouldShowUndoButton(
  outcome: QuickWinMechanicalOutcome | null | undefined,
): boolean {
  return outcome?.status === "applied" || outcome?.status === "partial";
}

/** Hide Fix with AI while a one-click mechanical apply is still available (pre-failure). */
export function shouldHideFixWithAiForMechanical(
  canApplyMechanical: boolean,
  outcome: QuickWinMechanicalOutcome | null | undefined,
): boolean {
  return canApplyMechanical && outcome == null;
}

export function formatMechanicalOutcomeReceipt(
  outcome: QuickWinMechanicalOutcome,
): { headline: string; details?: string[] } {
  switch (outcome.status) {
    case "applied":
      return { headline: `Applied · ${outcome.changes.join(", ")}` };
    case "partial":
      return {
        headline: `Partly applied · ${outcome.changes.join(", ")}`,
        details: outcome.unmet,
      };
    case "failed":
      return { headline: outcome.reason };
  }
}

interface QuickWinCardProps {
  issue: BlockingIssue;
  tailored?: TailoredResumeOutput | null;
  addressed?: boolean;
  outcome?: QuickWinMechanicalOutcome | null;
  onSkip: () => void;
  onFixWithAI?: () => void;
  onApplyMechanical?: () => void;
  onUndoMechanical?: () => void;
  /** When true, mechanical apply is available and Fix with AI should stay hidden until failure. */
  canApplyMechanical?: boolean;
}

export function QuickWinCard({
  issue,
  tailored,
  addressed = false,
  outcome = null,
  onSkip,
  onFixWithAI,
  onApplyMechanical,
  onUndoMechanical,
  canApplyMechanical = false,
}: QuickWinCardProps) {
  const preview = tailored ? previewMechanicalQuickWin(tailored, issue) : null;
  const willChange = formatMechanicalPreviewLine(preview);
  const receipt = outcome ? formatMechanicalOutcomeReceipt(outcome) : null;
  const hasOutcome = outcome !== null;
  const hideFixWithAi = shouldHideFixWithAiForMechanical(canApplyMechanical, outcome);

  return (
    <div
      className={cn(
        "border rounded-xl p-3 space-y-2 transition-colors",
        addressed
          ? "bg-slate-100/50 dark:bg-slate-800/50 border-slate-400 dark:border-slate-600/60 opacity-75"
          : "bg-emerald-400/5 border-emerald-400/20",
      )}
    >
      <div className="flex items-start gap-2">
        <Zap
          className={cn(
            "w-4 h-4 shrink-0 mt-0.5",
            addressed ? "text-slate-600 dark:text-slate-400" : "text-emerald-700 dark:text-emerald-400",
          )}
        />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <span
              className={cn(
                "text-[10px] uppercase tracking-wide font-semibold",
                addressed ? "text-slate-600 dark:text-slate-400" : "text-emerald-700 dark:text-emerald-400/80",
              )}
            >
              {CATEGORY_LABELS[issue.category]}
            </span>
            {addressed && (
              <span className="text-[10px] font-medium px-1.5 py-0.5 rounded bg-slate-200/80 dark:bg-slate-700/80 text-slate-600 dark:text-slate-400 border border-slate-400 dark:border-slate-600/60">
                Addressed
              </span>
            )}
          </div>
          <p className={cn("text-sm mt-0.5", addressed ? "text-slate-600 dark:text-slate-400" : "text-slate-800 dark:text-slate-200")}>
            {issue.description}
          </p>
          <p className={cn("text-xs mt-1", addressed ? "text-slate-600 dark:text-slate-400" : "text-slate-600 dark:text-slate-400")}>
            {issue.suggestion}
          </p>
          {shouldShowWillChangeLine(willChange, addressed || hasOutcome) && (
            <p className="text-xs mt-1.5 text-emerald-800 dark:text-emerald-200/90">
              <span className="font-semibold">Will change:</span> {willChange}
            </p>
          )}
          {receipt && (
            <div className="text-xs mt-1.5 space-y-0.5">
              <p
                className={cn(
                  outcome?.status === "failed"
                    ? "text-amber-800 dark:text-amber-200/90"
                    : "text-emerald-800 dark:text-emerald-200/90",
                )}
              >
                {receipt.headline}
              </p>
              {receipt.details && receipt.details.length > 0 && (
                <ul className="list-disc list-inside text-slate-600 dark:text-slate-400">
                  {receipt.details.map((detail) => (
                    <li key={detail}>{detail}</li>
                  ))}
                </ul>
              )}
            </div>
          )}
          {shouldShowEmployerConstraintCopy(addressed, hasOutcome) && (
            <p className="text-[11px] mt-1 text-slate-600 dark:text-slate-400">
              We only use employers already on your resume.
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {onApplyMechanical && !addressed && !hasOutcome && (
          <button
            type="button"
            onClick={onApplyMechanical}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-400/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold hover:bg-emerald-500/25 transition-colors"
          >
            <Check className="w-3 h-3" />
            Apply fix
          </button>
        )}
        {onUndoMechanical && shouldShowUndoButton(outcome) && (
          <button
            type="button"
            onClick={onUndoMechanical}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200/60 dark:bg-slate-700/60 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-300 dark:hover:bg-slate-600/60 transition-colors"
          >
            Undo
          </button>
        )}
        {onFixWithAI && !hideFixWithAi && (
          <button
            type="button"
            onClick={onFixWithAI}
            className={cn(
              "flex-1 flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors",
              addressed
                ? "bg-slate-200/60 dark:bg-slate-700/60 border border-slate-400 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:bg-slate-300 dark:hover:bg-slate-600/60 hover:text-slate-900 dark:hover:text-slate-200"
                : "bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/20 text-amber-700 dark:text-amber-400 hover:bg-amber-400/20",
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
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200/60 dark:bg-slate-700/60 border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-xs font-semibold hover:bg-red-100 dark:hover:bg-red-900/30 hover:text-red-400 transition-colors"
          >
            <X className="w-3 h-3" />
            Skip
          </button>
        )}
      </div>
    </div>
  );
}
