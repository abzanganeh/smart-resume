"use client";

import { useEffect, useState } from "react";
import { ChevronDown } from "lucide-react";
import type { EmployerTarget } from "@/lib/mechanicalFix";
import { cn } from "@/lib/utils";

interface RolePickerProps {
  targets: EmployerTarget[];
  triggerLabel?: string;
  confirmLabel?: string;
  onConfirm: (experienceIndex: number) => void;
  className?: string;
}

export function formatEmployerTargetLabel(target: EmployerTarget): string {
  if (target.company && target.title) return `${target.title} at ${target.company}`;
  return target.company || target.title || "Role";
}

export function RolePicker({
  targets,
  triggerLabel = "Choose a role",
  confirmLabel = "Add there",
  onConfirm,
  className,
}: RolePickerProps) {
  const [open, setOpen] = useState(false);
  const [selectedIndex, setSelectedIndex] = useState(targets[0]?.index ?? 0);

  useEffect(() => {
    if (targets.length > 0) {
      setSelectedIndex(targets[0]!.index);
    }
  }, [targets]);

  if (targets.length === 0) return null;

  return (
    <div className={cn("relative", className)}>
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex items-center justify-center gap-1.5 px-3 py-1.5 rounded-lg bg-slate-200/60 dark:bg-slate-700/60 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold hover:bg-slate-300 dark:hover:bg-slate-600/60 transition-colors"
      >
        {triggerLabel}
        <ChevronDown className="w-3 h-3" />
      </button>
      {open && (
        <div className="absolute z-20 mt-1 min-w-[14rem] rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 shadow-lg p-2 space-y-2">
          <select
            value={selectedIndex}
            onChange={(event) => setSelectedIndex(Number(event.target.value))}
            className="w-full rounded border border-slate-300 dark:border-slate-600 bg-white dark:bg-slate-950 px-2 py-1.5 text-xs text-slate-800 dark:text-slate-200"
          >
            {targets.map((target) => (
              <option key={target.index} value={target.index}>
                {formatEmployerTargetLabel(target)}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => {
              onConfirm(selectedIndex);
              setOpen(false);
            }}
            className="w-full px-3 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-400/30 text-emerald-700 dark:text-emerald-300 text-xs font-semibold hover:bg-emerald-500/25 transition-colors"
          >
            {confirmLabel}
          </button>
        </div>
      )}
    </div>
  );
}
