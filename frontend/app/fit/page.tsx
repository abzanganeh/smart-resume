"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertCircle,
  ArrowRight,
  Briefcase,
  History,
  Loader2,
  Lock,
  Plus,
  Search,
  Sparkles,
  Upload,
} from "lucide-react";
import { useRequireAuth } from "@/lib/auth/guards";
import { isSubscriptionActive } from "@/lib/billing";
import {
  getFitDetail,
  getFitHistory,
  getSubscriptionCurrent,
  streamFitAnalysis,
  type FitAnalysisOutput,
  type FitHistoryItem,
  type FitLabel,
} from "@/lib/api";
import { bulkInsertProfileChunks } from "@/lib/profile";
import { clsx } from "clsx";

type InputTab = "paste" | "upload" | "url";
type PageTab = "analyze" | "history";

const MAX_JD = 10_000;

const FIT_LABEL_STYLE: Record<
  FitLabel,
  { label: string; badge: string; gauge: string }
> = {
  strong: {
    label: "Strong",
    badge: "bg-emerald-500/20 text-emerald-700 dark:text-emerald-300 border-emerald-500/40",
    gauge: "stroke-emerald-400",
  },
  good: {
    label: "Good",
    badge: "bg-sky-500/20 text-sky-700 dark:text-sky-300 border-sky-500/40",
    gauge: "stroke-sky-400",
  },
  partial: {
    label: "Partial",
    badge: "bg-amber-500/20 text-amber-700 dark:text-amber-300 border-amber-500/40",
    gauge: "stroke-amber-400",
  },
  weak: {
    label: "Weak",
    badge: "bg-red-500/20 text-red-700 dark:text-red-300 border-red-500/40",
    gauge: "stroke-red-400",
  },
};

function FitScoreGauge({ score, fitLabel }: { score: number; fitLabel: FitLabel }) {
  const style = FIT_LABEL_STYLE[fitLabel];
  const radius = 54;
  const circumference = 2 * Math.PI * radius;
  const offset = circumference - (score / 100) * circumference;

  return (
    <div className="flex flex-col items-center gap-3">
      <div className="relative w-36 h-36">
        <svg className="w-full h-full -rotate-90" viewBox="0 0 120 120">
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            stroke="currentColor"
            strokeWidth="10"
            className="text-slate-800"
          />
          <circle
            cx="60"
            cy="60"
            r={radius}
            fill="none"
            strokeWidth="10"
            strokeLinecap="round"
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            className={style.gauge}
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-3xl font-bold text-slate-900 dark:text-white">{score}</span>
          <span className="text-xs text-slate-600 dark:text-slate-400">/ 100</span>
        </div>
      </div>
      <span
        className={clsx(
          "px-3 py-1 rounded-full text-sm font-semibold border",
          style.badge,
        )}
      >
        {style.label} fit
      </span>
    </div>
  );
}

function LockedState() {
  return (
    <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/80 p-10 text-center max-w-lg mx-auto">
      <Lock className="w-10 h-10 text-amber-700 dark:text-amber-400 mx-auto mb-4" />
      <h2 className="text-xl font-semibold text-slate-900 dark:text-white mb-2">Subscription required</h2>
      <p className="text-slate-600 dark:text-slate-400 text-sm mb-6">
        Job fit analysis compares your master resume against any job description using
        vector matching and AI — available on paid plans only.
      </p>
      <Link
        href="/billing"
        className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 transition-colors"
      >
        Upgrade to unlock
        <ArrowRight className="w-4 h-4" />
      </Link>
    </div>
  );
}

function FitResults({
  result,
  jdText,
  accessToken,
  onAddedBullets,
}: {
  result: FitAnalysisOutput;
  jdText: string;
  accessToken: string;
  onAddedBullets: () => void;
}) {
  const router = useRouter();
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);
  const [added, setAdded] = useState(false);

  const handleTailor = () => {
    const encoded = encodeURIComponent(jdText.slice(0, MAX_JD));
    router.push(`/session/new?step=jd&jd=${encoded}`);
  };

  const handleAddBullets = async () => {
    if (!result.suggested_master_resume_edits.length) return;
    setAdding(true);
    setAddError(null);
    try {
      await bulkInsertProfileChunks(
        accessToken,
        result.suggested_master_resume_edits.map((content) => ({
          content,
          section_type: "experience",
        })),
      );
      setAdded(true);
      onAddedBullets();
    } catch (e) {
      setAddError(e instanceof Error ? e.message : "Failed to add bullets.");
    } finally {
      setAdding(false);
    }
  };

  return (
    <div className="space-y-8">
      <div className="flex flex-col sm:flex-row gap-8 items-center sm:items-start">
        <FitScoreGauge score={result.overall_fit_score} fitLabel={result.fit_label} />
        <div className="flex-1 text-center sm:text-left">
          <pre className="text-slate-700 dark:text-slate-300 text-sm leading-relaxed whitespace-pre-wrap font-sans">
            {result.recommendation}
          </pre>
          <p className="mt-3 text-xs text-slate-600 dark:text-slate-400">
            {result.should_apply
              ? "Recommendation: worth applying with targeted resume tailoring."
              : "Recommendation: address key gaps before applying."}
          </p>
        </div>
      </div>

      {result.section_fits.length > 0 && (
        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Section breakdown</h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {result.section_fits.map((section) => (
              <div
                key={section.section_type}
                className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4"
              >
                <div className="flex items-center justify-between mb-2">
                  <span className="text-sm font-medium text-slate-900 dark:text-white capitalize">
                    {section.section_type.replace(/_/g, " ")}
                  </span>
                  <span className="text-sm font-mono text-amber-700 dark:text-amber-400">{section.match_score}%</span>
                </div>
                <div className="h-1.5 bg-slate-100 dark:bg-slate-800 rounded-full mb-3 overflow-hidden">
                  <div
                    className="h-full bg-amber-400 rounded-full transition-all"
                    style={{ width: `${section.match_score}%` }}
                  />
                </div>
                {section.matched_items.length > 0 && (
                  <ul className="text-xs text-emerald-700 dark:text-emerald-400/90 space-y-0.5 mb-2">
                    {section.matched_items.map((item) => (
                      <li key={item}>✓ {item}</li>
                    ))}
                  </ul>
                )}
                {section.missing_items.length > 0 && (
                  <ul className="text-xs text-red-700 dark:text-red-400/80 space-y-0.5">
                    {section.missing_items.map((item) => (
                      <li key={item}>✗ {item}</li>
                    ))}
                  </ul>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="grid sm:grid-cols-2 gap-6">
        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Key strengths</h3>
          <ul className="space-y-1.5">
            {result.key_strengths.map((s) => (
              <li key={s} className="text-sm text-slate-600 dark:text-slate-400 flex gap-2">
                <span className="text-emerald-700 dark:text-emerald-400 shrink-0">+</span>
                {s}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">Key gaps</h3>
          <ul className="space-y-1.5">
            {result.key_gaps.map((g) => (
              <li key={g} className="text-sm text-slate-600 dark:text-slate-400 flex gap-2">
                <span className="text-red-700 dark:text-red-400 shrink-0">−</span>
                {g}
              </li>
            ))}
          </ul>
        </div>
      </div>

      <div className="flex flex-wrap gap-3 pt-2">
        <button
          type="button"
          onClick={handleTailor}
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
        >
          <Sparkles className="w-4 h-4" />
          Tailor my resume for this job
        </button>
        <button
          type="button"
          disabled
          title="Coming in Release Phase 3"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-600 dark:text-slate-400 text-sm cursor-not-allowed"
        >
          <Search className="w-4 h-4" />
          Find similar jobs
          <span className="text-xs">(soon)</span>
        </button>
        {result.suggested_master_resume_edits.length > 0 && (
          <button
            type="button"
            onClick={handleAddBullets}
            disabled={adding || added}
            className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-300 dark:border-slate-700 text-slate-800 dark:text-slate-200 text-sm hover:border-slate-600 disabled:opacity-50"
          >
            {adding ? (
              <Loader2 className="w-4 h-4 animate-spin" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            {added ? "Added to master resume" : "Add suggested bullets to master resume"}
          </button>
        )}
      </div>
      {addError && (
        <p className="text-red-700 dark:text-red-400 text-sm flex items-center gap-2">
          <AlertCircle className="w-4 h-4" />
          {addError}
        </p>
      )}
    </div>
  );
}

function HistoryPanel({
  token,
  onSelect,
}: {
  token: string;
  onSelect: (id: string) => void;
}) {
  const [items, setItems] = useState<FitHistoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const data = await getFitHistory(token);
        if (!cancelled) setItems(data.items);
      } catch (e) {
        if (!cancelled) setError(e instanceof Error ? e.message : "Failed to load history.");
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  if (loading) {
    return (
      <div className="flex justify-center py-12 text-slate-600 dark:text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin" />
      </div>
    );
  }
  if (error) {
    return <p className="text-red-700 dark:text-red-400 text-sm text-center py-8">{error}</p>;
  }
  if (items.length === 0) {
    return (
      <p className="text-slate-600 dark:text-slate-400 text-sm text-center py-12">
        No analyses yet. Run your first fit check on the Analyze tab.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {items.map((item) => {
        const style = FIT_LABEL_STYLE[item.fit_label];
        return (
          <li key={item.id}>
            <button
              type="button"
              onClick={() => onSelect(item.id)}
              className="w-full text-left px-4 py-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:border-slate-700 transition-colors flex items-center justify-between gap-4"
            >
              <div>
                <span className="text-sm text-slate-900 dark:text-white font-medium">
                  Score {item.overall_fit_score} — {style.label}
                </span>
                <span className="block text-xs text-slate-600 dark:text-slate-400 mt-0.5">
                  {item.created_at
                    ? new Date(item.created_at).toLocaleString()
                    : "Unknown date"}
                </span>
              </div>
              <Briefcase className="w-4 h-4 text-slate-600 dark:text-slate-400 shrink-0" />
            </button>
          </li>
        );
      })}
    </ul>
  );
}

function FitPageContent() {
  const { session, status } = useRequireAuth("/fit");
  const [pageTab, setPageTab] = useState<PageTab>("analyze");
  const [inputTab, setInputTab] = useState<InputTab>("paste");
  const [subscribed, setSubscribed] = useState<boolean | null>(null);
  const [jdText, setJdText] = useState("");
  const [jdUrl, setJdUrl] = useState("");
  const [file, setFile] = useState<File | null>(null);
  const [analyzing, setAnalyzing] = useState(false);
  const [progressMsg, setProgressMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<FitAnalysisOutput | null>(null);
  const [resultJd, setResultJd] = useState("");

  const token = session?.backendAccessToken ?? "";

  const loadSubscription = useCallback(async () => {
    if (!token) return;
    try {
      const data = await getSubscriptionCurrent(token);
      const sub = data.subscription;
      setSubscribed(!!sub && isSubscriptionActive(sub.status));
    } catch {
      setSubscribed(false);
    }
  }, [token]);

  useEffect(() => {
    if (token) loadSubscription();
  }, [token, loadSubscription]);

  const handleAnalyze = async () => {
    if (!token) return;
    setError(null);
    setResult(null);
    setAnalyzing(true);
    setProgressMsg("Starting analysis…");

    const textToAnalyze = jdText.trim();

    if (inputTab === "paste" && !textToAnalyze) {
      setError("Paste a job description.");
      setAnalyzing(false);
      return;
    }
    if (inputTab === "upload" && !file) {
      setError("Choose a file to upload.");
      setAnalyzing(false);
      return;
    }
    if (inputTab === "url" && !textToAnalyze && !jdUrl.trim()) {
      setError("Enter a job posting URL.");
      setAnalyzing(false);
      return;
    }

    try {
      await streamFitAnalysis(
        token,
        {
          jd_text: inputTab !== "upload" ? textToAnalyze : undefined,
          jd_url: inputTab === "url" && !textToAnalyze ? jdUrl.trim() : undefined,
          file: inputTab === "upload" ? file ?? undefined : undefined,
        },
        (event) => {
          if (event.event === "progress" && event.message) {
            setProgressMsg(event.message);
          }
          if (event.event === "partial" && event.data) {
            setResult(event.data as FitAnalysisOutput);
          }
          if (event.event === "done" && event.output) {
            setResult(event.output as FitAnalysisOutput);
            const resolved = typeof event.jd_text === "string" ? event.jd_text : (textToAnalyze || jdText);
            setResultJd(resolved);
            if (resolved) setJdText(resolved);
          }
        },
      );
      if (!resultJd) setResultJd(textToAnalyze || jdText);
    } catch (e) {
      const err = e as Error & { code?: string };
      if (err.code === "subscription_required") {
        setSubscribed(false);
        setError("Subscription required for job fit analysis.");
      } else {
        setError(err.message ?? "Analysis failed.");
      }
    } finally {
      setAnalyzing(false);
      setProgressMsg(null);
    }
  };

  const handleHistorySelect = async (id: string) => {
    if (!token) return;
    setError(null);
    try {
      const detail = await getFitDetail(token, id);
      setResult(detail.result);
      setResultJd(detail.jd_text);
      setPageTab("analyze");
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load analysis.");
    }
  };

  if (status === "loading" || !session || subscribed === null) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
        <Loader2 className="w-6 h-6 animate-spin mr-2" />
        Loading…
      </div>
    );
  }

  if (subscribed === false) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
        <div className="max-w-3xl mx-auto px-6 py-12">
          <h1 className="text-2xl font-bold mb-2 flex items-center gap-2">
            <Briefcase className="w-7 h-7 text-amber-700 dark:text-amber-400" />
            Job fit analysis
          </h1>
          <p className="text-slate-600 dark:text-slate-400 text-sm mb-10">
            See how your master resume matches a job before tailoring.
          </p>
          <LockedState />
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
      <div className="max-w-3xl mx-auto px-6 py-12">
        <h1 className="text-2xl font-bold mb-2 flex items-center gap-2">
          <Briefcase className="w-7 h-7 text-amber-700 dark:text-amber-400" />
          Job fit analysis
        </h1>
        <p className="text-slate-600 dark:text-slate-400 text-sm mb-8">
          Compare your master resume against any job — powered by vector matching and AI.
        </p>

        <div className="flex gap-2 mb-6 border-b border-slate-200 dark:border-slate-800 pb-2">
          <button
            type="button"
            onClick={() => setPageTab("analyze")}
            className={clsx(
              "px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              pageTab === "analyze"
                ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300",
            )}
          >
            Analyze
          </button>
          <button
            type="button"
            onClick={() => setPageTab("history")}
            className={clsx(
              "inline-flex items-center gap-1.5 px-4 py-2 text-sm font-medium rounded-lg transition-colors",
              pageTab === "history"
                ? "bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-white"
                : "text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300",
            )}
          >
            <History className="w-4 h-4" />
            History
          </button>
        </div>

        {pageTab === "history" ? (
          <HistoryPanel token={token} onSelect={handleHistorySelect} />
        ) : (
          <>
            {!result && (
              <>
                <div className="flex gap-2 mb-4">
                  {(
                    [
                      ["paste", "Paste JD"],
                      ["upload", "Upload file"],
                      ["url", "Enter URL"],
                    ] as const
                  ).map(([tab, label]) => (
                    <button
                      key={tab}
                      type="button"
                      onClick={() => setInputTab(tab)}
                      className={clsx(
                        "px-3 py-1.5 text-xs font-medium rounded-lg border transition-colors",
                        inputTab === tab
                          ? "border-amber-400/60 bg-amber-500/10 dark:bg-amber-400/10 text-amber-700 dark:text-amber-300"
                          : "border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400 hover:border-slate-700",
                      )}
                    >
                      {label}
                    </button>
                  ))}
                </div>

                {inputTab === "paste" && (
                  <textarea
                    value={jdText}
                    onChange={(e) => setJdText(e.target.value)}
                    placeholder="Paste the full job description…"
                    className="w-full h-56 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 text-slate-800 dark:text-slate-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600 mb-2"
                  />
                )}

                {inputTab === "upload" && (
                  <label className="flex flex-col items-center justify-center h-40 border-2 border-dashed border-slate-300 dark:border-slate-700 rounded-xl bg-white/50 dark:bg-slate-900/50 cursor-pointer hover:border-slate-600 mb-2">
                    <Upload className="w-8 h-8 text-slate-600 dark:text-slate-400 mb-2" />
                    <span className="text-sm text-slate-600 dark:text-slate-400">
                      {file ? file.name : "PDF, DOCX, or TXT"}
                    </span>
                    <input
                      type="file"
                      accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                      className="hidden"
                      onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                    />
                  </label>
                )}

                {inputTab === "url" && (
                  <input
                    value={jdUrl}
                    onChange={(e) => setJdUrl(e.target.value)}
                    placeholder="https://jobs.example.com/backend-engineer"
                    className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl px-4 py-3 text-slate-800 dark:text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600 mb-2"
                  />
                )}

                {inputTab === "paste" && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 mb-4">
                    {jdText.length.toLocaleString()} / {MAX_JD.toLocaleString()} characters
                  </p>
                )}

                <button
                  type="button"
                  onClick={handleAnalyze}
                  disabled={analyzing}
                  className="w-full py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 flex items-center justify-center gap-2"
                >
                  {analyzing ? (
                    <>
                      <Loader2 className="w-4 h-4 animate-spin" />
                      {progressMsg ?? "Analyzing…"}
                    </>
                  ) : (
                    "Analyze fit"
                  )}
                </button>
              </>
            )}

            {error && (
              <div className="mt-4 flex items-start gap-2 text-red-700 dark:text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
                <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
                {error}
              </div>
            )}

            {result && (
              <div className="mt-6">
                <div className="flex justify-end mb-4">
                  <button
                    type="button"
                    onClick={() => {
                      setResult(null);
                      setResultJd("");
                      setJdText("");
                      setFile(null);
                      setJdUrl("");
                    }}
                    className="text-xs text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300"
                  >
                    ← New analysis
                  </button>
                </div>
                <FitResults
                  result={result}
                  jdText={resultJd || jdText}
                  accessToken={token}
                  onAddedBullets={() => {}}
                />
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

export default function FitPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
          Loading…
        </div>
      }
    >
      <FitPageContent />
    </Suspense>
  );
}
