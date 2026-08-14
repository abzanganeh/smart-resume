"use client";

import { ChevronDown, ChevronUp, Sparkles } from "lucide-react";

interface Props {
  phaseRunning: boolean;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  modelLabel?: string | null;
}

export function SessionAiControls({
  phaseRunning,
  open,
  onOpenChange,
  modelLabel,
}: Props) {
  const summary = modelLabel
    ? `Platform AI · ${modelLabel}`
    : "Platform AI · included with your plan";

  return (
    <div className="mb-6 rounded-xl border border-slate-700 bg-slate-800/40 overflow-hidden">
      <button
        type="button"
        onClick={() => onOpenChange(!open)}
        className="w-full flex items-center gap-3 px-4 py-3 text-left hover:bg-slate-800/80 transition-colors"
      >
        <Sparkles className="w-4 h-4 text-amber-400 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-xs font-semibold text-slate-400 uppercase tracking-wide">AI for this session</p>
          <p className="text-sm text-slate-200 truncate">{summary}</p>
        </div>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
        )}
      </button>

      {open && (
        <div className="px-4 pb-4 pt-1 border-t border-slate-700 space-y-4">
          <p className="text-xs text-slate-500">
            Phase 3 model quality is determined by your subscription tier. Upgrade your plan on{" "}
            <a href="/billing" className="text-amber-400 hover:underline">
              Billing
            </a>{" "}
            for higher-quality AI.
          </p>
          {phaseRunning && (
            <p className="text-xs text-amber-400/90">AI is running — settings are locked until the phase completes.</p>
          )}
        </div>
      )}
    </div>
  );
}
