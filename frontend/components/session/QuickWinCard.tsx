"use client";

import { Check, MessageSquare, X, Zap } from "lucide-react";
import type { BlockingIssue, TailoredResumeOutput } from "@/lib/api";
import {
  previewMechanicalQuickWin,
  type MechanicalFixPreview,
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

export function shouldShowEmployerConstraintCopy(addressed: boolean): boolean {
  return !addressed;
}

interface QuickWinCardProps {
  issue: BlockingIssue;
  tailored?: TailoredResumeOutput | null;
  addressed?: boolean;
  onSkip: () => void;
  onFixWithAI?: () => void;
  onApplyMechanical?: () => void;
}

export function QuickWinCard({
  issue,
  tailored,
  addressed = false,
  onSkip,
  onFixWithAI,
  onApplyMechanical,
}: QuickWinCardProps) {
  const preview = tailored ? previewMechanicalQuickWin(tailored, issue) : null;
  const willChange = formatMechanicalPreviewLine(preview);

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
          {shouldShowWillChangeLine(willChange, addressed) && (
            <p className="text-xs mt-1.5 text-emerald-800 dark:text-emerald-200/90">
              <span className="font-semibold">Will change:</span> {willChange}
            </p>
          )}
          {shouldShowEmployerConstraintCopy(addressed) && (
            <p className="text-[11px] mt-1 text-slate-600 dark:text-slate-400">
              We only use employers already on your resume.
            </p>
          )}
        </div>
      </div>

      <div className="flex gap-2 flex-wrap">
        {onApplyMechanical && !addressed && (
          <button
            type="button"
            onClick={onApplyMechanical}
            className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-400/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold hover:bg-emerald-500/25 transition-colors"
          >
            <Check className="w-3 h-3" />
            Apply fix
          </button>
        )}
        {onFixWithAI && (
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
