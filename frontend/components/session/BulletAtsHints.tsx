"use client";

import { Pencil, X } from "lucide-react";
import type { BlockingIssue } from "@/lib/api";
import { issueKey } from "@/lib/issueAnchors";
import { cn } from "@/lib/utils";

interface Props {
  issues: BlockingIssue[];
  skippedKeys: ReadonlySet<string>;
  addressedKeys: ReadonlySet<string>;
  onEditBullet: () => void;
  onIgnore: (issues: BlockingIssue[]) => void;
}

function uniqueSuggestions(issues: BlockingIssue[]): string[] {
  const seen = new Set<string>();
  const lines: string[] = [];
  for (const issue of issues) {
    const text = issue.suggestion.trim();
    if (!text || seen.has(text)) continue;
    seen.add(text);
    lines.push(text);
  }
  return lines;
}

export function BulletAtsHints({
  issues,
  skippedKeys,
  addressedKeys,
  onEditBullet,
  onIgnore,
}: Props) {
  if (issues.length === 0) return null;

  const anchorKey = issueKey(issues[0]!);
  const ignored = skippedKeys.has(anchorKey);
  const edited = addressedKeys.has(anchorKey);
  const suggestions = uniqueSuggestions(issues);

  if (ignored) {
    return (
      <div className="ml-5 rounded border border-slate-300/80 dark:border-slate-600/80 bg-slate-100/60 dark:bg-slate-800/40 px-2.5 py-1.5">
        <p className="text-[11px] text-slate-500 dark:text-slate-400 italic">
          Ignored wording suggestions for this bullet.
        </p>
      </div>
    );
  }

  if (edited) {
    return (
      <div className="ml-5 rounded border border-emerald-400/30 bg-emerald-500/10 px-2.5 py-1.5">
        <p className="text-[11px] text-emerald-800 dark:text-emerald-200">
          Bullet updated — click <strong>Recalculate ATS score</strong> on Export to refresh issues.
        </p>
      </div>
    );
  }

  return (
    <div
      className="ml-5 rounded border border-amber-400/35 bg-amber-500/10 dark:bg-amber-400/10 px-2.5 py-2 space-y-2"
    >
      <p className="text-[10px] font-semibold uppercase tracking-wide text-amber-800/80 dark:text-amber-200/80">
        Wording polish ({suggestions.length} note{suggestions.length === 1 ? "" : "s"})
      </p>
      <ul className="space-y-1 list-disc list-inside text-xs text-amber-950 dark:text-amber-50 leading-relaxed">
        {suggestions.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
      <p className="text-[10px] text-amber-800/70 dark:text-amber-200/70">
        Nothing is applied until you edit and save the bullet. Use Ignore if this wording is fine as-is.
      </p>
      <div className="flex items-center gap-2 flex-wrap">
        <button
          type="button"
          onClick={onEditBullet}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold",
            "bg-amber-500 text-slate-900 hover:bg-amber-400 transition-colors",
          )}
        >
          <Pencil className="w-3 h-3" />
          Edit bullet
        </button>
        <button
          type="button"
          onClick={() => onIgnore(issues)}
          className={cn(
            "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-[11px] font-semibold",
            "bg-slate-200/90 dark:bg-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600 transition-colors",
          )}
        >
          <X className="w-3 h-3" />
          Ignore
        </button>
      </div>
    </div>
  );
}
