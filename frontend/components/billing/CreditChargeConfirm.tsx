"use client";

import { Zap } from "lucide-react";
import { cn } from "@/lib/utils";

interface CreditChargeConfirmProps {
  costCredits?: number;
  actionLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  disabled?: boolean;
  confirmLabel?: string;
  className?: string;
}

export function CreditChargeConfirm({
  costCredits = 1,
  actionLabel,
  onConfirm,
  onCancel,
  disabled = false,
  confirmLabel = "Confirm",
  className,
}: CreditChargeConfirmProps) {
  const creditLabel = costCredits === 1 ? "credit" : "credits";

  return (
    <div className={cn("flex flex-wrap items-center gap-2", className)}>
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/30 text-xs text-amber-700 dark:text-amber-300">
        <Zap className="w-3.5 h-3.5 shrink-0" />
        {actionLabel} costs {costCredits} {creditLabel}
      </div>
      <button
        type="button"
        onClick={onConfirm}
        disabled={disabled}
        className="px-3 py-1.5 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-40"
      >
        {confirmLabel}
      </button>
      <button
        type="button"
        onClick={onCancel}
        disabled={disabled}
        className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
      >
        Cancel
      </button>
    </div>
  );
}
