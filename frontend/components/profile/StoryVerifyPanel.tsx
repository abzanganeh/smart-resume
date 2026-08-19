"use client";

import { AlertTriangle, CheckCircle2 } from "lucide-react";
import type { VerifyItem } from "@/lib/story";
import { cn } from "@/lib/utils";

interface Props {
  items: VerifyItem[];
  reviewCount: number;
  attestationChecked: boolean;
  onAttestationChange: (checked: boolean) => void;
}

export function StoryVerifyPanel({
  items,
  reviewCount,
  attestationChecked,
  onAttestationChange,
}: Props) {
  if (items.length === 0) {
    return (
      <div className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4 text-sm text-slate-600 dark:text-slate-400">
        No employer or date hints detected — still review the full draft before saving.
      </div>
    );
  }

  return (
    <div className="rounded-xl border border-slate-300 dark:border-slate-700 bg-slate-100/40 dark:bg-slate-800/40 p-4 space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            Verify names &amp; dates
          </p>
          <p className="text-xs text-slate-600 dark:text-slate-400 mt-1">
            Compare what you said with what landed in the resume. Fix anything that looks off.
          </p>
        </div>
        {reviewCount > 0 ? (
          <span className="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-amber-800 dark:text-amber-300 bg-amber-100 dark:bg-amber-950/40 px-2 py-1 rounded-full">
            <AlertTriangle className="w-3 h-3" />
            {reviewCount} to review
          </span>
        ) : (
          <span className="shrink-0 inline-flex items-center gap-1 text-xs font-medium text-green-800 dark:text-green-300 bg-green-100 dark:bg-green-950/40 px-2 py-1 rounded-full">
            <CheckCircle2 className="w-3 h-3" />
            All matched
          </span>
        )}
      </div>

      <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
        {items.map((item, idx) => (
          <div
            key={`${item.field}-${idx}-${item.spoken}`}
            className={cn(
              "rounded-lg border px-3 py-2 text-xs",
              item.status === "review"
                ? "border-amber-400/40 bg-amber-50/80 dark:bg-amber-950/20"
                : "border-slate-300/60 dark:border-slate-700 bg-white/60 dark:bg-slate-900/40",
            )}
          >
            <div className="flex items-center justify-between gap-2 mb-1">
              <span className="font-medium text-slate-700 dark:text-slate-300">{item.field}</span>
              <span
                className={cn(
                  "uppercase tracking-wide text-[10px] font-semibold",
                  item.status === "review" ? "text-amber-700 dark:text-amber-400" : "text-green-700 dark:text-green-400",
                )}
              >
                {item.status}
              </span>
            </div>
            <div className="grid gap-1 sm:grid-cols-2 text-slate-600 dark:text-slate-400">
              <p><span className="text-slate-500 dark:text-slate-500">You said:</span> {item.spoken}</p>
              <p><span className="text-slate-500 dark:text-slate-500">Resume:</span> {item.resume}</p>
            </div>
            <p className="mt-1 text-slate-700 dark:text-slate-300">{item.message}</p>
          </div>
        ))}
      </div>

      <label className="flex items-start gap-3 cursor-pointer group">
        <input
          type="checkbox"
          checked={attestationChecked}
          onChange={(e) => onAttestationChange(e.target.checked)}
          className="mt-0.5 h-4 w-4 rounded border-slate-400 text-amber-500 focus:ring-amber-400"
        />
        <span className="text-sm text-slate-700 dark:text-slate-300 group-hover:text-slate-900 dark:group-hover:text-white">
          I confirm employer names, job titles, dates, and skills in this resume are accurate.
        </span>
      </label>
    </div>
  );
}
