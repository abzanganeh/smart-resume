"use client";

import { ChevronDown, ChevronUp, AlertTriangle, CheckCircle2, XCircle } from "lucide-react";
import { useState } from "react";

import type { ScoreAxis } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  axes: ScoreAxis[];
  /** Group axes by family for the recruiter-style layout the user asked for. */
  defaultOpen?: boolean;
}

const STATUS_COLOR: Record<ScoreAxis["status"], string> = {
  pass: "text-emerald-700 dark:text-emerald-400",
  warn: "text-amber-700 dark:text-amber-400",
  fail: "text-red-700 dark:text-red-400",
};

const STATUS_BG: Record<ScoreAxis["status"], string> = {
  pass: "bg-emerald-400/10 border-emerald-400/30",
  warn: "bg-amber-500/10 dark:bg-amber-400/10 border-amber-400/30",
  fail: "bg-red-400/10 border-red-400/30",
};

const STATUS_ICON: Record<ScoreAxis["status"], typeof CheckCircle2> = {
  pass: CheckCircle2,
  warn: AlertTriangle,
  fail: XCircle,
};

/**
 * Three-bucket grouping mirrors the score model in `phase4_score.py`:
 *   ATS-Readability axes drive parser-based scoring,
 *   Content Quality axes drive recruiter scan,
 *   Polish axes catch resume-writing-101 mistakes.
 */
const AXIS_GROUPS: { title: string; subtitle: string; keys: string[] }[] = [
  {
    title: "ATS readability",
    subtitle: "What the parser sees",
    keys: [
      "keyword_presence",
      "keyword_dual_placement",
      "section_completeness",
      "contact_completeness",
      "field_completeness",
    ],
  },
  {
    title: "Content quality",
    subtitle: "What a recruiter scans for",
    keys: [
      "bullet_metrics",
      "action_verbs",
      "bullet_length",
      "resume_length",
    ],
  },
  {
    title: "Polish",
    subtitle: "Resume-writing fundamentals",
    keys: ["weak_phrases", "first_person", "buzzwords"],
  },
];

function AxisRow({ axis }: { axis: ScoreAxis }) {
  const [open, setOpen] = useState(axis.status !== "pass");
  const Icon = STATUS_ICON[axis.status];
  const pct = axis.max === 0 ? 0 : Math.max(0, Math.min(100, (axis.score / axis.max) * 100));

  return (
    <div className={cn("border rounded-lg overflow-hidden", STATUS_BG[axis.status])}>
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center gap-3 px-3 py-2 hover:bg-white/[0.02] text-left"
      >
        <Icon className={cn("w-4 h-4 shrink-0", STATUS_COLOR[axis.status])} />
        <span className="text-slate-800 dark:text-slate-200 text-sm flex-1 truncate">{axis.label}</span>
        <span className={cn("tabular-nums text-sm font-semibold", STATUS_COLOR[axis.status])}>
          {axis.score.toFixed(1)} / {axis.max.toFixed(0)}
        </span>
        {open ? (
          <ChevronUp className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" />
        ) : (
          <ChevronDown className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" />
        )}
      </button>
      <div className="h-1 bg-slate-100 dark:bg-slate-800">
        <div
          className={cn(
            "h-full transition-all",
            axis.status === "pass"
              ? "bg-emerald-400"
              : axis.status === "warn"
              ? "bg-amber-400"
              : "bg-red-400",
          )}
          style={{ width: `${pct}%` }}
        />
      </div>
      {open && (
        <div className="px-3 py-2.5 border-t border-slate-200 dark:border-slate-800/60 bg-slate-50/40 dark:bg-slate-950/40 space-y-2">
          {axis.summary && (
            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">{axis.summary}</p>
          )}
          {axis.issues.length > 0 && (
            <ul className="space-y-1 text-xs text-slate-700 dark:text-slate-300">
              {axis.issues.map((issue, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <span className="text-slate-600 dark:text-slate-400 leading-tight">•</span>
                  <span className="leading-relaxed">{issue}</span>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}

export function ScoreBreakdownPanel({ axes, defaultOpen = false }: Props) {
  const [open, setOpen] = useState(defaultOpen);

  if (!axes || axes.length === 0) return null;

  const totalScore = axes.reduce((acc, a) => acc + a.score, 0);
  const totalMax = axes.reduce((acc, a) => acc + a.max, 0);
  const failCount = axes.filter((a) => a.status === "fail").length;
  const warnCount = axes.filter((a) => a.status === "warn").length;

  const byKey = new Map(axes.map((a) => [a.key, a]));

  return (
    <section className="border border-slate-300 dark:border-slate-700 rounded-xl bg-white/40 dark:bg-slate-900/40 overflow-hidden">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="w-full flex items-center justify-between gap-3 px-4 py-3 bg-slate-100/40 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800 text-left"
      >
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-slate-900 dark:text-slate-100">Score breakdown</span>
          <span className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">
            {totalScore.toFixed(1)} / {totalMax.toFixed(0)}
          </span>
        </div>
        <div className="flex items-center gap-2 text-xs">
          {failCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-red-400/15 text-red-700 dark:text-red-300 border border-red-400/30">
              {failCount} failing
            </span>
          )}
          {warnCount > 0 && (
            <span className="px-1.5 py-0.5 rounded bg-amber-500/15 dark:bg-amber-400/15 text-amber-700 dark:text-amber-300 border border-amber-400/30">
              {warnCount} warning
            </span>
          )}
          {open ? (
            <ChevronUp className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-slate-600 dark:text-slate-400" />
          )}
        </div>
      </button>
      {open && (
        <div className="p-4 space-y-4">
          {AXIS_GROUPS.map((group) => {
            const groupAxes = group.keys.map((k) => byKey.get(k)).filter(Boolean) as ScoreAxis[];
            if (groupAxes.length === 0) return null;
            const groupScore = groupAxes.reduce((acc, a) => acc + a.score, 0);
            const groupMax = groupAxes.reduce((acc, a) => acc + a.max, 0);
            return (
              <div key={group.title} className="space-y-2">
                <div className="flex items-baseline justify-between">
                  <div>
                    <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200">{group.title}</h3>
                    <p className="text-[11px] text-slate-600 dark:text-slate-400">{group.subtitle}</p>
                  </div>
                  <span className="text-xs font-semibold tabular-nums text-slate-700 dark:text-slate-300">
                    {groupScore.toFixed(1)} / {groupMax.toFixed(0)}
                  </span>
                </div>
                <div className="space-y-1.5">
                  {groupAxes.map((axis) => (
                    <AxisRow key={axis.key} axis={axis} />
                  ))}
                </div>
              </div>
            );
          })}
        </div>
      )}
    </section>
  );
}
