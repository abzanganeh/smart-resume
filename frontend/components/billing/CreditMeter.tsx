"use client";

import { cn } from "@/lib/utils";

interface CreditMeterProps {
  used: number;
  cap: number;
  label?: string;
  compact?: boolean;
  className?: string;
}

export function CreditMeter({
  used,
  cap,
  label = "Credits",
  compact = false,
  className,
}: CreditMeterProps) {
  const safeCap = Math.max(cap, 1);
  const pct = Math.min(100, Math.round((used / safeCap) * 100));
  const remaining = Math.max(0, cap - used);

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
          {used}/{cap}
          {!compact && <span className="text-slate-500 dark:text-slate-500 ml-1">({pct}%)</span>}
        </span>
      </div>
      <div
        className={cn(
          "bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden",
          compact ? "h-1.5" : "h-2",
        )}
        role="progressbar"
        aria-valuenow={used}
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
