"use client";

import { Check, Pencil, RotateCw, Trash2, X } from "lucide-react";
import {
  HIGHLIGHT,
  toneForSuggestion,
  type HighlightTone,
} from "@/lib/suggestionHighlight";
import type { ResumeSuggestion } from "@/lib/suggestions";

// ── Shared UI ─────────────────────────────────────────────────────────────────

export function SuggestionActionButtons({
  onAccept,
  onReject,
  acceptLabel = "Accept",
  rejectLabel = "Ignore",
}: {
  onAccept: () => void;
  onReject: () => void;
  acceptLabel?: string;
  rejectLabel?: string;
}) {
  return (
    <div className="flex gap-1.5 shrink-0">
      <button
        type="button"
        onClick={onAccept}
        className="flex items-center gap-1 px-2 py-0.5 rounded bg-emerald-700 hover:bg-emerald-600 text-white text-[11px] font-medium transition-colors"
      >
        <Check className="w-3 h-3" />
        {acceptLabel}
      </button>
      <button
        type="button"
        onClick={onReject}
        className="flex items-center gap-1 px-2 py-0.5 rounded bg-slate-700 hover:bg-slate-600 text-slate-300 text-[11px] transition-colors"
      >
        <X className="w-3 h-3" />
        {rejectLabel}
      </button>
    </div>
  );
}

function HighlightBox({
  tone,
  children,
  className = "",
}: {
  tone: HighlightTone;
  children: React.ReactNode;
  className?: string;
}) {
  if (tone === "none") return <>{children}</>;
  return (
    <div className={`${HIGHLIGHT[tone]} rounded-lg px-2.5 py-2 ${className}`}>
      {children}
    </div>
  );
}

// ── Summary ───────────────────────────────────────────────────────────────────

export function SummaryHighlight({
  currentText,
  suggestion,
  onAccept,
  onReject,
  children,
}: {
  currentText: string;
  suggestion?: ResumeSuggestion;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  children: React.ReactNode;
}) {
  if (!suggestion) return <>{children}</>;

  const tone = toneForSuggestion(suggestion);
  const proposed = suggestion.patch.new_summary ?? "";

  if (tone === "accepted") {
    return (
      <HighlightBox tone="accepted">
        {children}
      </HighlightBox>
    );
  }

  if (tone === "rejected") {
    return <>{children}</>;
  }

  return (
    <div className="space-y-2">
      <p className="text-slate-400 text-sm leading-relaxed line-through opacity-60">{currentText}</p>
      <HighlightBox tone="pending">
        <p className="text-amber-100 text-sm leading-relaxed whitespace-pre-wrap">{proposed}</p>
        <div className="flex justify-end mt-2">
          <SuggestionActionButtons
            onAccept={() => onAccept(suggestion.id)}
            onReject={() => onReject(suggestion.id)}
          />
        </div>
      </HighlightBox>
    </div>
  );
}

// ── Skill chip ────────────────────────────────────────────────────────────────

export function SkillChip({
  skill,
  tone,
  suggestion,
  onAccept,
  onReject,
}: {
  skill: string;
  tone: HighlightTone;
  suggestion?: ResumeSuggestion;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const base =
    tone === "accepted"
      ? "bg-emerald-900/40 border-emerald-500/50 text-emerald-200"
      : tone === "pending"
        ? "bg-amber-900/40 border-amber-500/50 text-amber-200"
        : tone === "rejected"
          ? "bg-red-900/30 border-red-600/50 text-red-300 line-through"
          : "bg-slate-800 border-slate-700 text-slate-300";

  const isPendingRemove =
    tone === "pending" &&
    !!suggestion?.patch.remove_skills?.some(
      (name) => name.toLowerCase() === skill.toLowerCase(),
    );

  return (
    <span className={`inline-flex items-center gap-1 rounded px-2 py-0.5 text-xs border ${base}`}>
      {isPendingRemove ? (
        <>
          <span className="line-through">{skill}</span>
          {suggestion && (
            <SuggestionActionButtons
              onAccept={() => onAccept(suggestion.id)}
              onReject={() => onReject(suggestion.id)}
            />
          )}
        </>
      ) : tone === "pending" ? (
        <>+ {skill}</>
      ) : (
        skill
      )}
    </span>
  );
}

// ── Experience / project bullet row ───────────────────────────────────────────

export function SuggestedBulletRow({
  suggestion,
  originalText,
  displayText,
  tone,
  phaseRunning,
  onAccept,
  onReject,
  onRegen,
  onEdit,
  onDelete,
}: {
  suggestion?: ResumeSuggestion;
  originalText?: string;
  displayText: string;
  tone: HighlightTone;
  phaseRunning?: boolean;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  onRegen?: () => void;
  onEdit?: () => void;
  onDelete?: () => void;
}) {
  const isPendingEdit =
    suggestion?.status === "pending" &&
    !!suggestion.patch.bullet_old &&
    !!suggestion.patch.bullet_new;

  const isPendingProjectEdit =
    suggestion?.status === "pending" &&
    !!suggestion.patch.project_bullet_old &&
    !!suggestion.patch.project_bullet_new;

  const proposed =
    suggestion?.patch.bullet_new ??
    suggestion?.patch.project_bullet_new ??
    displayText;

  if (isPendingEdit || isPendingProjectEdit) {
    return (
      <div className={`${HIGHLIGHT.pending} rounded-lg px-2.5 py-2 space-y-1.5`}>
        <div className="flex items-start gap-2">
          <span className="text-red-400/80 mt-0.5 shrink-0">•</span>
          <p className="flex-1 text-red-300/80 text-sm leading-relaxed line-through">
            {originalText ?? suggestion?.patch.bullet_old ?? suggestion?.patch.project_bullet_old}
          </p>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-amber-400 mt-0.5 shrink-0">•</span>
          <p className="flex-1 text-amber-100 text-sm leading-relaxed">{proposed}</p>
        </div>
        <div className="flex justify-end">
          <SuggestionActionButtons
            onAccept={() => onAccept(suggestion!.id)}
            onReject={() => onReject(suggestion!.id)}
          />
        </div>
      </div>
    );
  }

  const textClass =
    tone === "accepted"
      ? "text-emerald-100"
      : tone === "rejected"
        ? "text-red-300 line-through"
        : "text-slate-200";

  return (
    <div className={`group flex items-start gap-2 ${tone !== "none" ? HIGHLIGHT[tone] + " rounded-lg px-2 py-1.5" : ""}`}>
      <span className="text-slate-500 mt-1 shrink-0">•</span>
      <p className={`flex-1 text-sm leading-relaxed ${textClass}`}>{displayText}</p>
      {(onRegen || onEdit || onDelete) && (
        <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition shrink-0">
          {onRegen && (
            <button
              type="button"
              disabled={phaseRunning}
              onClick={onRegen}
              className="p-1 rounded text-slate-500 hover:text-amber-400 disabled:opacity-40"
              title="Regenerate bullet"
            >
              <RotateCw className="w-3.5 h-3.5" />
            </button>
          )}
          {onEdit && (
            <button
              type="button"
              onClick={onEdit}
              className="p-1 rounded text-slate-500 hover:text-amber-400"
              title="Edit bullet"
            >
              <Pencil className="w-3.5 h-3.5" />
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              onClick={onDelete}
              className="p-1 rounded text-slate-500 hover:text-red-400"
              title="Delete bullet"
            >
              <Trash2 className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// ── Pending new content (project, replace-all) ────────────────────────────────

export function PendingAdditionCard({
  suggestion,
  onAccept,
  onReject,
  children,
}: {
  suggestion: ResumeSuggestion;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
  children: React.ReactNode;
}) {
  if (suggestion.status === "accepted") {
    return <HighlightBox tone="accepted">{children}</HighlightBox>;
  }
  if (suggestion.status === "rejected") {
    return <HighlightBox tone="rejected">{children}</HighlightBox>;
  }
  return (
    <HighlightBox tone="pending">
      {children}
      <div className="flex justify-end mt-2">
        <SuggestionActionButtons
          onAccept={() => onAccept(suggestion.id)}
          onReject={() => onReject(suggestion.id)}
        />
      </div>
    </HighlightBox>
  );
}

// ── Experience title / dates inline ───────────────────────────────────────────

export function InlineFieldSuggestion({
  current,
  suggestion,
  label,
  onAccept,
  onReject,
}: {
  current: string;
  suggestion?: ResumeSuggestion;
  label: string;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  if (!suggestion || suggestion.status === "rejected") {
    return <span>{current}</span>;
  }

  const proposed =
    label === "title"
      ? suggestion.patch.new_title
      : label === "dates"
        ? suggestion.patch.new_dates
        : label === "name"
          ? suggestion.patch.new_name
          : suggestion.patch.new_institution;

  if (!proposed) return <span>{current}</span>;

  if (suggestion.status === "accepted") {
    return (
      <span className={`${HIGHLIGHT.accepted} rounded px-1.5 py-0.5 text-emerald-100`}>
        {current}
      </span>
    );
  }

  return (
    <span className="inline-flex flex-col gap-1">
      <span className="text-slate-500 line-through text-xs">{current}</span>
      <span className={`${HIGHLIGHT.pending} rounded px-1.5 py-0.5 text-amber-100 text-xs inline-flex items-center gap-2`}>
        {proposed}
        <SuggestionActionButtons
          onAccept={() => onAccept(suggestion.id)}
          onReject={() => onReject(suggestion.id)}
        />
      </span>
    </span>
  );
}

// ── Orphan fallback ───────────────────────────────────────────────────────────

function orphanPatchPreview(patch: import("@/lib/api").ResumePatch): string[] {
  const lines: string[] = [];
  if (patch.delete_experience) lines.push(`Remove experience entry (${patch.company ?? "unknown"})`);
  for (const name of patch.remove_projects ?? []) lines.push(`Remove project: ${name}`);
  for (const name of patch.remove_certifications ?? []) lines.push(`Remove certification: ${name}`);
  if (patch.new_institution) lines.push(`Institution → ${patch.new_institution}`);
  if (patch.new_degree) lines.push(`Degree → ${patch.new_degree}`);
  if (patch.new_dates) lines.push(`Dates → ${patch.new_dates}`);
  if (patch.new_title) lines.push(`Title → ${patch.new_title}`);
  for (const s of patch.add_education_bullets ?? []) lines.push(`+ ${s}`);
  for (const s of patch.add_skills ?? []) lines.push(`+ skill: ${s}`);
  if (patch.new_summary) lines.push(patch.new_summary);
  if (lines.length === 0 && patch.description) lines.push(patch.description);
  return lines;
}

export function OrphanSuggestionCard({
  suggestion,
  onAccept,
  onReject,
}: {
  suggestion: ResumeSuggestion;
  onAccept: (id: string) => void;
  onReject: (id: string) => void;
}) {
  const tone = toneForSuggestion(suggestion);
  const preview = orphanPatchPreview(suggestion.patch);
  return (
    <HighlightBox tone={tone === "none" ? "pending" : tone}>
      <p className="text-[10px] font-semibold text-amber-400/80 uppercase tracking-wider mb-1">
        AI suggestion
      </p>
      <div className="space-y-1 mb-2">
        {preview.map((line, i) => (
          <p key={i} className="text-slate-300 text-xs">{line}</p>
        ))}
      </div>
      {suggestion.status === "pending" && (
        <div className="flex justify-end">
          <SuggestionActionButtons
            onAccept={() => onAccept(suggestion.id)}
            onReject={() => onReject(suggestion.id)}
          />
        </div>
      )}
      {suggestion.status === "accepted" && (
        <p className="text-emerald-400 text-xs flex items-center gap-1">
          <Check className="w-3 h-3" /> Applied
        </p>
      )}
    </HighlightBox>
  );
}
