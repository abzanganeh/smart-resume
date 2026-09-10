"use client";

import { cn } from "@/lib/utils";

interface CreditMeterProps {
  used: number;
  cap: number;
  label?: string;
  compact?: boolean;
  /** When true, show remaining/cap instead of consumed/cap (for “Credits left”). */
  showRemaining?: boolean;
  className?: string;
}

export function CreditMeter({
  used,
  cap,
  label = "Credits",
  compact = false,
  showRemaining = false,
  className,
}: CreditMeterProps) {
  const safeCap = Math.max(cap, 1);
  const consumed = Math.min(safeCap, Math.max(0, used));
  const remaining = Math.max(0, safeCap - consumed);
  const displayNumerator = showRemaining ? remaining : consumed;
  const pct = Math.min(100, Math.round((displayNumerator / safeCap) * 100));

  return (
    <div className={cn("min-w-0", className)}>
      <div
        className={cn(
          "flex justify-between text-xs text-slate-600 dark:text-slate-400",
          compact ? "mb-0.5" : "mb-1",
        )}
      >
        <span className="truncate">{label}</span>
        <span className="tabular-nums shrink-0 ml-2">
          {displayNumerator}/{cap}
          {!compact && <span className="text-slate-500 dark:text-slate-500 ml-1">({pct}%)</span>}
        </span>
      </div>
      <div
        className={cn(
          "bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden",
          compact ? "h-1.5" : "h-2",
        )}
        role="progressbar"
        aria-valuenow={showRemaining ? remaining : consumed}
        aria-valuemin={0}
        aria-valuemax={cap}
        aria-label={`${label}: ${remaining} remaining`}
      >
        <div
          className="h-full bg-amber-400 rounded-full transition-all"
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}
