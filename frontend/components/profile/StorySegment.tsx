"use client";

import { Mic, Trash2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface Props {
  index: number;
  text: string;
  isRecording: boolean;
  disabled: boolean;
  onChange: (text: string) => void;
  onReRecord: () => void;
  onDelete: () => void;
}

export function StorySegment({ index, text, isRecording, disabled, onChange, onReRecord, onDelete }: Props) {
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
