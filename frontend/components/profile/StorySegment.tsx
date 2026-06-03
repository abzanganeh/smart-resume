"use client";

import { Mic, Sparkles, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  index: number;
  text: string;
  isRecording: boolean;
  disabled: boolean;
  coachOpen: boolean;
  onChange: (text: string) => void;
  onReRecord: () => void;
  onDelete: () => void;
  onCoach: () => void;
}

export function StorySegment({
  index,
  text,
  isRecording,
  disabled,
  coachOpen,
  onChange,
  onReRecord,
  onDelete,
  onCoach,
}: Props) {
  const preview = text.slice(0, 80) + (text.length > 80 ? "…" : "");

  return (
    <div className={cn(
      "rounded-xl border p-4 space-y-2 transition-colors",
      isRecording ? "border-red-500/50 bg-red-500/5" : "border-slate-700 bg-slate-800/40",
    )}>
      <div className="flex items-center justify-between gap-2">
        <span className="text-xs font-semibold text-slate-500 uppercase tracking-wide">
          Segment {index + 1}
        </span>
        <div className="flex items-center gap-1.5">
          {/* Coach me button — only visible when segment has content */}
          {text.trim().length > 10 && !isRecording && (
            <button
              type="button"
              onClick={onCoach}
              disabled={disabled}
              title={coachOpen ? "Close coach" : "Get coaching feedback"}
              className={cn(
                "flex items-center gap-1 px-2 py-1 rounded-lg text-xs font-medium transition-colors disabled:opacity-40",
                coachOpen
                  ? "bg-indigo-600 text-white hover:bg-indigo-500"
                  : "text-indigo-400 hover:text-indigo-200 hover:bg-indigo-900/40 border border-indigo-700/50",
              )}
            >
              <Sparkles className="w-3 h-3" />
              Coach me
            </button>
          )}
          <button
            type="button"
            onClick={onReRecord}
            disabled={disabled}
            title="Re-record this segment"
            className="p-1.5 rounded-lg text-slate-500 hover:text-amber-400 hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            <Mic className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onDelete}
            disabled={disabled}
            title="Delete this segment"
            className="p-1.5 rounded-lg text-slate-500 hover:text-red-400 hover:bg-slate-700 disabled:opacity-40 transition-colors"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {isRecording ? (
        <p className="text-red-400 text-xs italic animate-pulse">Recording…</p>
      ) : (
        <textarea
          value={text}
          onChange={(e) => onChange(e.target.value)}
          disabled={disabled}
          rows={3}
          placeholder="Segment transcript will appear here…"
          className="w-full bg-slate-900 border border-slate-700 rounded-lg p-3 text-slate-200 text-sm resize-y focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600 disabled:opacity-60"
        />
      )}

      {!isRecording && text.length === 0 && (
        <p className="text-slate-600 text-xs italic">{preview || "Empty segment"}</p>
      )}
    </div>
  );
}
