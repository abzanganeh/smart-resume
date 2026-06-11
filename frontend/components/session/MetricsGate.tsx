"use client";

import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, ChevronDown, ChevronUp, Loader2, ShieldCheck, X } from "lucide-react";
import { saveApprovedMetrics, type ApprovedMetric, type SuspiciousMetric } from "@/lib/api";
import { cn } from "@/lib/utils";

const REASON_LABELS: Record<SuspiciousMetric["reason"], string> = {
  round_percentage: "Round % — no baseline",
  dollar_claim: "Dollar claim — no source",
  stacked_metrics: "3+ metrics in one bullet",
  no_source: "Likely AI-inherited number",
};

interface ScopeEntry {
  scope: string;
  flags: SuspiciousMetric[];
  metric: string;
  source_note: string;
}

interface Props {
  sessionId: string;
  unverifiedMetrics: SuspiciousMetric[];
  initialApprovedMetrics: ApprovedMetric[];
  onSaved: (metrics: ApprovedMetric[]) => void;
}

function buildInitialEntries(
  flags: SuspiciousMetric[],
  approved: ApprovedMetric[]
): ScopeEntry[] {
  const approvedByScope = new Map<string, ApprovedMetric>(
    approved.map((a) => [a.scope, a])
  );

  const byScope = new Map<string, SuspiciousMetric[]>();
  for (const f of flags) {
    const list = byScope.get(f.scope) ?? [];
    list.push(f);
    byScope.set(f.scope, list);
  }

  return Array.from(byScope.entries()).map(([scope, scopeFlags]) => {
    const prior = approvedByScope.get(scope);
    return {
      scope,
      flags: scopeFlags,
      metric: prior?.metric ?? "",
      source_note: prior?.source_note ?? "",
    };
  });
}

export function MetricsGate({
  sessionId,
  unverifiedMetrics,
  initialApprovedMetrics,
  onSaved,
}: Props) {
  const [entries, setEntries] = useState<ScopeEntry[]>(() =>
    buildInitialEntries(unverifiedMetrics, initialApprovedMetrics)
  );
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [savedOk, setSavedOk] = useState(false);

  // Re-initialise if the audit result changes (e.g. user re-runs Phase 2).
  useEffect(() => {
    setEntries(buildInitialEntries(unverifiedMetrics, initialApprovedMetrics));
    setSavedOk(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [unverifiedMetrics.length]);

  const toggleExpand = (scope: string) => {
    setExpanded((prev) => {
      const next = new Set(prev);
      next.has(scope) ? next.delete(scope) : next.add(scope);
      return next;
    });
  };

  const updateEntry = (scope: string, field: "metric" | "source_note", value: string) => {
    setEntries((prev) =>
      prev.map((e) => (e.scope === scope ? { ...e, [field]: value } : e))
    );
    setSavedOk(false);
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const metrics: ApprovedMetric[] = entries
        .filter((e) => e.metric.trim())
        .map((e) => ({
          scope: e.scope,
          metric: e.metric.trim(),
          source_note: e.source_note.trim(),
        }));
      await saveApprovedMetrics(sessionId, metrics);
      setSavedOk(true);
      onSaved(metrics);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save metrics.");
    } finally {
      setSaving(false);
    }
  };

  const filledCount = entries.filter((e) => e.metric.trim()).length;

  if (unverifiedMetrics.length === 0) return null;

  return (
    <section className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-4 space-y-3">
      <div className="flex items-start gap-3">
        <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
        <div className="flex-1 min-w-0">
          <p className="text-sm font-semibold text-amber-300">
            Unverifiable metrics detected ({unverifiedMetrics.length})
          </p>
          <p className="text-xs text-slate-400 mt-0.5">
            Phase 3 found numbers that appear inherited from a previous AI rewrite. Replace each with a metric you can back up — or leave blank to move it to <span className="text-amber-300">Metrics Needed</span>. Phase 3 will not carry forward unconfirmed numbers.
          </p>
        </div>
      </div>

      <div className="space-y-2">
        {entries.map((entry) => {
          const isOpen = expanded.has(entry.scope);
          const hasFilled = Boolean(entry.metric.trim());
          return (
            <div
              key={entry.scope}
              className={cn(
                "rounded-lg border text-sm transition-colors",
                hasFilled
                  ? "border-emerald-500/30 bg-emerald-500/5"
                  : "border-slate-700 bg-slate-900/60"
              )}
            >
              {/* Scope header row */}
              <button
                onClick={() => toggleExpand(entry.scope)}
                className="w-full flex items-center justify-between gap-2 px-3 py-2.5 text-left"
              >
                <div className="flex items-center gap-2 min-w-0">
                  {hasFilled ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
                  ) : (
                    <ShieldCheck className="w-4 h-4 text-slate-500 shrink-0" />
                  )}
                  <span className="font-medium text-slate-200 truncate">{entry.scope}</span>
                  <span className="text-xs text-slate-500 shrink-0">
                    {entry.flags.length} flag{entry.flags.length !== 1 ? "s" : ""}
                  </span>
                </div>
                {isOpen ? (
                  <ChevronUp className="w-4 h-4 text-slate-500 shrink-0" />
                ) : (
                  <ChevronDown className="w-4 h-4 text-slate-500 shrink-0" />
                )}
              </button>

              {isOpen && (
                <div className="px-3 pb-3 space-y-3 border-t border-slate-700/50 pt-3">
                  {/* Flagged bullets */}
                  <div className="space-y-1.5">
                    {entry.flags.map((f, i) => (
                      <div key={i} className="flex items-start gap-2">
                        <span className="mt-0.5 shrink-0 text-[10px] font-medium px-1.5 py-0.5 rounded bg-amber-400/15 text-amber-300 uppercase tracking-wide">
                          {REASON_LABELS[f.reason]}
                        </span>
                        <p className="text-xs text-slate-400 leading-relaxed">{f.bullet}</p>
                      </div>
                    ))}
                  </div>

                  {/* User input */}
                  <div className="space-y-2">
                    <div>
                      <label className="block text-xs text-slate-400 mb-1">
                        Verified metric <span className="text-slate-600">(e.g. "Test F1 0.64 on 1.8M transactions")</span>
                      </label>
                      <input
                        type="text"
                        value={entry.metric}
                        onChange={(e) => updateEntry(entry.scope, "metric", e.target.value)}
                        placeholder="Leave blank to move to Metrics Needed"
                        className="w-full rounded-md bg-slate-800 border border-slate-600 px-2.5 py-1.5 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-slate-400"
                      />
                    </div>
                    <div>
                      <label className="block text-xs text-slate-500 mb-1">
                        Source note <span className="text-slate-600">(optional — not sent to AI, for your reference)</span>
                      </label>
                      <input
                        type="text"
                        value={entry.source_note}
                        onChange={(e) => updateEntry(entry.scope, "source_note", e.target.value)}
                        placeholder="e.g. eval_run_2025.json · row 42"
                        className="w-full rounded-md bg-slate-800 border border-slate-700 px-2.5 py-1.5 text-sm text-slate-400 placeholder-slate-700 focus:outline-none focus:border-slate-500"
                      />
                    </div>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {error && (
        <div className="flex items-center gap-2 text-xs text-red-400">
          <X className="w-3.5 h-3.5 shrink-0" />
          {error}
        </div>
      )}

      <div className="flex items-center justify-between pt-1">
        <p className="text-xs text-slate-500">
          {filledCount} of {entries.length} confirmed
          {filledCount < entries.length && (
            <span className="text-slate-600">
              {" "}· {entries.length - filledCount} will go to Metrics Needed
            </span>
          )}
        </p>
        <button
          onClick={handleSave}
          disabled={saving}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
            savedOk
              ? "bg-emerald-600/20 text-emerald-300 border border-emerald-600/30"
              : "bg-slate-700 hover:bg-slate-600 text-slate-200 border border-slate-600"
          )}
        >
          {saving ? (
            <Loader2 className="w-3.5 h-3.5 animate-spin" />
          ) : savedOk ? (
            <CheckCircle2 className="w-3.5 h-3.5" />
          ) : null}
          {saving ? "Saving…" : savedOk ? "Saved" : "Confirm & save"}
        </button>
      </div>
    </section>
  );
}
