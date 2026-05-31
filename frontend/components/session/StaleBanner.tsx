"use client";

import { AlertTriangle } from "lucide-react";

interface Props {
  message: string;
  onRerun: () => void;
  running?: boolean;
}

export function StaleBanner({ message, onRerun, running }: Props) {
  return (
    <div className="flex flex-col sm:flex-row sm:items-center gap-3 bg-amber-400/10 border border-amber-400/30 rounded-lg px-4 py-3 mb-6">
      <div className="flex items-start gap-2 flex-1 text-amber-200 text-sm">
        <AlertTriangle className="w-4 h-4 shrink-0 mt-0.5 text-amber-400" />
        <span>{message}</span>
      </div>
      <button
        type="button"
        onClick={onRerun}
        disabled={running}
        className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300 disabled:opacity-50 whitespace-nowrap"
      >
        {running ? "Running…" : "Re-run"}
      </button>
    </div>
  );
}
