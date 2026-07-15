"use client";

import { type PhaseRunScope, type TailoredResumeOutput } from "@/lib/api";
import type { EntryIssueBadge } from "@/lib/issueAnchors";
import { TailoredEditor } from "./TailoredEditor";
import type { ResumeSuggestion } from "@/lib/suggestions";

interface Props {
  tailored: TailoredResumeOutput | null;
  streaming: boolean;
  costInfo?: { cost_formatted: string; provider: string; model: string } | null;
  sessionId: string;
  /** Bump when chat (or external) replaces the full tailored doc so the editor re-syncs. */
  editorRevision?: number;
  onEdited?: (
    updated: TailoredResumeOutput,
    meta?: { source: "edit" | "undo" | "redo" },
  ) => void;
  onVersionSnapshot?: (version: number) => void;
  onScopedRun?: (scope: PhaseRunScope) => void;
  phaseRunning?: boolean;
  suggestionDraft?: string | null;
  onClearSuggestion?: () => void;
  suggestions?: ResumeSuggestion[];
  onAcceptSuggestion?: (id: string) => void;
  onAcceptAllSuggestions?: () => void;
  onRejectSuggestion?: (id: string) => void;
  onDismissSuggestion?: (id: string) => void;
  entryIssueBadges?: Record<string, EntryIssueBadge>;
}

export function ResumeDiff({ tailored, streaming, costInfo, sessionId, editorRevision = 0, onEdited, onVersionSnapshot, onScopedRun, phaseRunning, suggestionDraft, onClearSuggestion, suggestions, onAcceptSuggestion, onAcceptAllSuggestions, onRejectSuggestion, onDismissSuggestion, entryIssueBadges }: Props) {
  if (streaming && !tailored) {
    return (
      <div className="space-y-3">
        {costInfo && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm text-slate-300">
            Estimated cost:{" "}
            <span className="text-amber-400 font-semibold">{costInfo.cost_formatted}</span>
            <span className="text-slate-500 ml-2">
              ({costInfo.provider} · {costInfo.model})
            </span>
          </div>
        )}
        <div className="flex flex-col items-center gap-3 py-12 text-slate-400">
          <div className="w-7 h-7 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
          <p className="text-sm">Rewriting resume sections…</p>
          <p className="text-xs text-slate-600">This takes 20–60 seconds depending on resume length.</p>
        </div>
      </div>
    );
  }
  if (!tailored) return null;

  return (
    <div className="space-y-4">
      {costInfo && (
        <div className="bg-slate-800 border border-slate-700 rounded-lg p-3 text-sm text-slate-300">
          Rewrite cost:{" "}
          <span className="text-amber-400 font-semibold">{costInfo.cost_formatted}</span>
          <span className="text-slate-500 ml-2">
            ({costInfo.provider} · {costInfo.model})
          </span>
        </div>
      )}
      <TailoredEditor
        initial={tailored}
        sessionId={sessionId}
        editorSyncKey={editorRevision}
        onSaved={onEdited}
        onVersionSnapshot={onVersionSnapshot}
        onScopedRun={onScopedRun}
        phaseRunning={phaseRunning}
        suggestionDraft={suggestionDraft}
        onClearSuggestion={onClearSuggestion}
        suggestions={suggestions}
        onAcceptSuggestion={onAcceptSuggestion}
        onAcceptAllSuggestions={onAcceptAllSuggestions}
        onRejectSuggestion={onRejectSuggestion}
        onDismissSuggestion={onDismissSuggestion}
        entryIssueBadges={entryIssueBadges}
      />
    </div>
  );
}
