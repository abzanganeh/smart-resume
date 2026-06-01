"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Info, Plus, Save } from "lucide-react";
import { saveAdditions, patchAuditOutput, type AuditOutput, type BulletFixPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  output: AuditOutput | null;
  streaming: boolean;
  sessionId: string;
  /** Claimed keywords restored from the server on mount. */
  initialClaimedKeywords?: string[];
  /** Extra notes restored from the server on mount. */
  initialExtraNotes?: string;
  /** Bullet fixes restored from the server on mount. */
  initialBulletFixes?: BulletFixPayload[];
  onAdditionsSaved?: () => void;
  onReaudit?: () => void;
  onAuditEdited?: (stale: Record<string, string | null>) => void;
}

const SEVERITY_CONFIG = {
  high: { icon: AlertCircle, cls: "text-red-400 bg-red-400/10 border-red-400/20" },
  medium: { icon: AlertTriangle, cls: "text-amber-400 bg-amber-400/10 border-amber-400/20" },
  low: { icon: Info, cls: "text-blue-400 bg-blue-400/10 border-blue-400/20" },
};

export function AuditPanel({
  output,
  streaming,
  sessionId,
  initialClaimedKeywords,
  initialExtraNotes,
  initialBulletFixes,
  onAdditionsSaved,
  onReaudit,
  onAuditEdited,
}: Props) {
  const [claimedKeywords, setClaimedKeywords] = useState<Set<string>>(
    () => new Set(initialClaimedKeywords ?? [])
  );
  const [extraNotes, setExtraNotes] = useState(initialExtraNotes ?? "");
  const [saving, setSaving] = useState(false);
  const [savedOk, setSavedOk] = useState(false);

  // Per-bullet fix drafts: key = bullet index, value = corrected text.
  const [bulletFixes, setBulletFixes] = useState<Record<number, string>>(() => {
    const initial: Record<number, string> = {};
    (initialBulletFixes ?? []).forEach((bf, idx) => {
      initial[idx] = bf.suggestion;
    });
    return initial;
  });
  const [expandedFix, setExpandedFix] = useState<number | null>(null);
  const [summaryDraft, setSummaryDraft] = useState("");
  const [editingSummary, setEditingSummary] = useState(false);
  const [summarySaving, setSummarySaving] = useState(false);
  const fixRefs = useRef<Record<number, HTMLTextAreaElement | null>>({});

  // Re-hydrate when session data arrives from the parent (e.g. first render or refresh).
  useEffect(() => {
    if (initialClaimedKeywords && initialClaimedKeywords.length > 0) {
      setClaimedKeywords(new Set(initialClaimedKeywords));
    }
    if (initialExtraNotes) {
      setExtraNotes(initialExtraNotes);
    }
  }, [initialClaimedKeywords, initialExtraNotes]);

  // Debounced auto-save bullet fixes whenever they change (500 ms).
  const bulletFixDebounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (bulletFixDebounceRef.current) clearTimeout(bulletFixDebounceRef.current);
    bulletFixDebounceRef.current = setTimeout(() => {
      if (!output) return;
      const fixes: BulletFixPayload[] = Object.entries(bulletFixes)
        .filter(([, suggestion]) => suggestion.trim())
        .map(([idxStr, suggestion]) => {
          const idx = Number(idxStr);
          const original = output.bullet_issues?.[idx]?.original ?? "";
          return { original, suggestion };
        });
      void saveAdditions(sessionId, {
        claimed_keywords: Array.from(claimedKeywords),
        extra_notes: extraNotes,
        bullet_fixes: fixes,
      });
    }, 500);
    return () => {
      if (bulletFixDebounceRef.current) clearTimeout(bulletFixDebounceRef.current);
    };
    // Only re-run when bulletFixes change (not on every claimedKeywords/extraNotes change
    // to avoid competing debounces — the explicit "Save my additions" button covers those).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bulletFixes]);

  async function saveSummaryEdit() {
    if (!output) return;
    setSummarySaving(true);
    try {
      const res = await patchAuditOutput(sessionId, { summary: summaryDraft.trim() });
      onAuditEdited?.(res.stale);
      setEditingSummary(false);
    } finally {
      setSummarySaving(false);
    }
  }

  // ProgressLog in the parent handles loading UI.
  if (!output) return null;

  // Defensive — LLM may return a partial object
  const coverage = output.keyword_coverage ?? { present: [], missing_must_have: [], missing_nice_to_have: [] };
  const missingMust = coverage.missing_must_have ?? [];
  const missingNice = coverage.missing_nice_to_have ?? [];
  const allMissing = [...missingMust, ...missingNice];

  const scoreColor =
    output.overall_score >= 70
      ? "text-green-400"
      : output.overall_score >= 45
      ? "text-amber-400"
      : "text-red-400";

  function toggleKeyword(kw: string) {
    setClaimedKeywords((prev) => {
      const next = new Set(prev);
      next.has(kw) ? next.delete(kw) : next.add(kw);
      return next;
    });
    setSavedOk(false);
  }

  async function handleSave() {
    setSaving(true);
    try {
      const fixes: BulletFixPayload[] = Object.entries(bulletFixes)
        .filter(([, suggestion]) => suggestion.trim())
        .map(([idxStr, suggestion]) => {
          const idx = Number(idxStr);
          const original = output?.bullet_issues?.[idx]?.original ?? "";
          return { original, suggestion };
        });
      await saveAdditions(sessionId, {
        claimed_keywords: Array.from(claimedKeywords),
        extra_notes: extraNotes.trim(),
        bullet_fixes: fixes,
      });
      setSavedOk(true);
      onAdditionsSaved?.();
    } finally {
      setSaving(false);
    }
  }

  const hasAdditions = claimedKeywords.size > 0 || extraNotes.trim().length > 0;

  return (
    <div className="space-y-6">

      {/* Score */}
      <div className="bg-slate-800 border border-slate-700 rounded-xl p-4 flex items-center justify-between">
        <div>
          <p className="text-slate-400 text-sm">Audit Score</p>
          <p className={cn("text-3xl font-bold mt-0.5", scoreColor)}>
            {output.overall_score}
            <span className="text-slate-500 text-lg font-normal"> / 100</span>
          </p>
        </div>
        <div className="text-right text-sm text-slate-400">
          <p>{output.page_estimate}</p>
          {output.page_limit_exceeded && (
            <p className="text-red-400 text-xs mt-0.5">Page limit exceeded</p>
          )}
        </div>
      </div>

      {/* Summary */}
      {output.summary && (
        <div className="text-slate-300 text-sm bg-slate-800 border border-slate-700 rounded-lg p-3">
          {editingSummary ? (
            <div className="space-y-2">
              <textarea
                value={summaryDraft}
                onChange={(e) => setSummaryDraft(e.target.value)}
                rows={3}
                className="w-full bg-slate-900 border border-amber-400/50 rounded-lg px-3 py-2 text-sm text-slate-200 resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
              />
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={saveSummaryEdit}
                  disabled={summarySaving}
                  className="px-3 py-1 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-50"
                >
                  {summarySaving ? "Saving…" : "Save audit edit"}
                </button>
                <button
                  type="button"
                  onClick={() => setEditingSummary(false)}
                  className="px-3 py-1 rounded-lg bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <div className="flex items-start justify-between gap-3">
              <p>{output.summary}</p>
              <button
                type="button"
                onClick={() => {
                  setSummaryDraft(output.summary);
                  setEditingSummary(true);
                }}
                className="text-xs text-amber-400 hover:text-amber-300 shrink-0"
              >
                Edit
              </button>
            </div>
          )}
        </div>
      )}

      {/* ── Missing keywords ─────────────────────────────────────────────── */}
      {allMissing.length > 0 && (
        <div className="bg-slate-800/60 border border-slate-700 rounded-xl p-5 space-y-4">
          <div>
            <h3 className="text-slate-100 font-semibold mb-1 text-sm">Missing Keywords</h3>
            <p className="text-slate-400 text-xs leading-relaxed">
              These keywords appear in the job description but not in your resume.
              <strong className="text-amber-300"> Check any that you actually have</strong> — the rewrite
              will include them. Items you don't check will be flagged as genuinely missing.
            </p>
          </div>

          {missingMust.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-red-400 uppercase tracking-wider mb-2">
                Must-have ({missingMust.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {missingMust.map((kw) => {
                  const checked = claimedKeywords.has(kw);
                  return (
                    <button
                      key={kw}
                      type="button"
                      onClick={() => toggleKeyword(kw)}
                      className={cn(
                        "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all",
                        checked
                          ? "bg-emerald-900/40 border-emerald-600 text-emerald-300"
                          : "bg-red-500/10 border-red-500/30 text-red-300 hover:border-red-400"
                      )}
                    >
                      {checked ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : (
                        <Plus className="h-3.5 w-3.5 opacity-50" />
                      )}
                      {kw}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {missingNice.length > 0 && (
            <div>
              <p className="text-xs font-semibold text-amber-400 uppercase tracking-wider mb-2">
                Nice-to-have ({missingNice.length})
              </p>
              <div className="flex flex-wrap gap-2">
                {missingNice.map((kw) => {
                  const checked = claimedKeywords.has(kw);
                  return (
                    <button
                      key={kw}
                      type="button"
                      onClick={() => toggleKeyword(kw)}
                      className={cn(
                        "flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg border text-xs font-medium transition-all",
                        checked
                          ? "bg-emerald-900/40 border-emerald-600 text-emerald-300"
                          : "bg-amber-400/10 border-amber-400/30 text-amber-300 hover:border-amber-400"
                      )}
                    >
                      {checked ? (
                        <CheckCircle2 className="h-3.5 w-3.5" />
                      ) : (
                        <Plus className="h-3.5 w-3.5 opacity-50" />
                      )}
                      {kw}
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Free-text additions */}
          <div>
            <label className="text-xs font-semibold text-slate-400 uppercase tracking-wider block mb-2">
              Anything else to add? (optional)
            </label>
            <textarea
              value={extraNotes}
              onChange={(e) => { setExtraNotes(e.target.value); setSavedOk(false); }}
              placeholder="e.g. I have 2 years of Kubernetes experience and have led teams of 5+, but it's not in my resume yet."
              rows={3}
              className="w-full px-3 py-2.5 rounded-lg border border-slate-600 bg-slate-900 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:ring-2 focus:ring-amber-400/50 resize-none"
            />
          </div>

          {/* Save additions */}
          <div className="space-y-3">
            <div className="flex items-center gap-3 flex-wrap">
              <button
                type="button"
                onClick={handleSave}
                disabled={saving || !hasAdditions}
                className="flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-400 hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed text-slate-900 text-sm font-semibold transition-colors"
              >
                <Save className="h-4 w-4" />
                {saving ? "Saving…" : "Save my additions"}
              </button>
              {claimedKeywords.size > 0 && !savedOk && (
                <span className="text-xs text-slate-500">
                  {claimedKeywords.size} item{claimedKeywords.size !== 1 ? "s" : ""} selected — save to update the score
                </span>
              )}
            </div>

            {/* After saving: prompt to re-audit */}
            {savedOk && (
              <div className="flex items-center gap-3 bg-emerald-900/20 border border-emerald-500/30 rounded-lg px-4 py-3">
                <CheckCircle2 className="h-4 w-4 text-emerald-400 shrink-0" />
                <div className="flex-1 text-xs text-slate-300">
                  <span className="text-emerald-400 font-semibold">Saved.</span>{" "}
                  Recalculate your audit score with these additions applied.
                </div>
                {onReaudit && (
                  <button
                    type="button"
                    onClick={onReaudit}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors whitespace-nowrap"
                  >
                    Recalculate Audit Score →
                  </button>
                )}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Bullet issues ──────────────────────────────────────────────────── */}
      {(output.bullet_issues ?? []).length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-1 text-sm">
            Bullet Issues ({output.bullet_issues.length})
          </h3>
          <p className="text-slate-500 text-xs mb-3">
            Click <strong className="text-slate-400">Fix this bullet</strong> to write a corrected version — it will be passed to the rewrite.
          </p>
          <div className="space-y-3">
            {output.bullet_issues.map((issue, i) => {
              const cfg = SEVERITY_CONFIG[issue.severity as keyof typeof SEVERITY_CONFIG] ?? SEVERITY_CONFIG.medium;
              const Icon = cfg.icon;
              const isOpen = expandedFix === i;
              const hasFix = !!bulletFixes[i]?.trim();
              return (
                <div key={i} className={cn("border rounded-xl p-3 text-sm space-y-2", cfg.cls)}>
                  <div className="flex items-start gap-2">
                    <Icon className="w-4 h-4 shrink-0 mt-0.5" />
                    <div className="flex-1 min-w-0">
                      <p className="font-medium text-xs opacity-70 mb-1">
                        {issue.section}
                        {issue.company ? ` · ${issue.company}` : ""} · bullet {issue.bullet_index + 1}
                      </p>
                      {/* Original text: break-words fixes overflow for long concatenated strings */}
                      <p className="opacity-90 break-words overflow-wrap-anywhere whitespace-pre-wrap">
                        "{issue.original}"
                      </p>
                      <div className="flex flex-wrap gap-1 mt-1.5">
                        {(issue.issues ?? []).map((iss, j) => (
                          <span key={j} className="text-xs bg-black/20 rounded px-1.5 py-0.5">
                            {iss.replace(/_/g, " ")}
                          </span>
                        ))}
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => {
                        setExpandedFix(isOpen ? null : i);
                        if (!isOpen) {
                          setBulletFixes((p) => ({ ...p, [i]: p[i] ?? issue.original }));
                          setTimeout(() => fixRefs.current[i]?.focus(), 50);
                        }
                      }}
                      className={cn(
                        "shrink-0 px-2.5 py-1 rounded-lg text-xs font-medium transition-colors border",
                        hasFix
                          ? "bg-emerald-900/40 border-emerald-600 text-emerald-300"
                          : "bg-black/20 border-black/30 text-current hover:bg-black/30"
                      )}
                    >
                      {hasFix ? "✓ Fixed" : "Fix this bullet"}
                    </button>
                  </div>

                  {isOpen && (
                    <div className="space-y-1.5 pt-1">
                      <p className="text-xs opacity-60">Your corrected version (will be given to the AI rewrite):</p>
                      <textarea
                        ref={(el) => { fixRefs.current[i] = el; }}
                        value={bulletFixes[i] ?? issue.original}
                        onChange={(e) => setBulletFixes((p) => ({ ...p, [i]: e.target.value }))}
                        rows={3}
                        className="w-full bg-slate-900/80 border border-slate-600 rounded-lg px-3 py-2 text-slate-200 text-xs resize-none focus:outline-none focus:ring-1 focus:ring-amber-400"
                      />
                      <div className="flex gap-2">
                        <button
                          type="button"
                          onClick={() => setExpandedFix(null)}
                          className="px-3 py-1 rounded bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300"
                        >
                          Done
                        </button>
                        <button
                          type="button"
                          onClick={() => { setBulletFixes((p) => { const n = { ...p }; delete n[i]; return n; }); setExpandedFix(null); }}
                          className="px-3 py-1 rounded bg-slate-700 text-slate-300 text-xs hover:bg-slate-600"
                        >
                          Clear fix
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          {/* Show user fixes summary so they can be passed to the rewrite phase */}
          {Object.keys(bulletFixes).length > 0 && (
            <p className="mt-3 text-xs text-slate-500 flex items-center gap-1.5">
              <CheckCircle2 className="h-3.5 w-3.5 text-emerald-400" />
              {Object.keys(bulletFixes).length} bullet fix{Object.keys(bulletFixes).length !== 1 ? "es" : ""} saved — the AI rewrite will use them as guidance.
            </p>
          )}
        </div>
      )}

      {/* ── Clichés ──────────────────────────────────────────────────────── */}
      {(output.cliches_found ?? []).length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-2 text-sm">Clichés to Remove</h3>
          <div className="flex flex-wrap gap-1.5">
            {output.cliches_found.map((c, i) => (
              <span
                key={i}
                className="bg-amber-400/10 border border-amber-400/30 text-amber-300 rounded px-2 py-0.5 text-xs line-through"
              >
                {c}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* ── Contact issues ───────────────────────────────────────────────── */}
      {(output.contact_issues ?? []).length > 0 && (
        <div>
          <h3 className="text-slate-200 font-semibold mb-2 text-sm">Contact Issues</h3>
          {output.contact_issues.map((c, i) => (
            <p key={i} className="text-red-400 text-sm">
              {c}
            </p>
          ))}
        </div>
      )}
    </div>
  );
}
