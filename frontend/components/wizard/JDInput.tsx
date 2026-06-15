"use client";

import { useEffect, useRef, useState } from "react";
import { AlertCircle, AlertTriangle } from "lucide-react";
import { type JDPayload } from "@/lib/api";
import { uncertainJdHostLabel } from "@/lib/jdCompleteness";

interface Props {
  onSubmit: (payload: JDPayload) => void;
  selectedProvider: string;
  selectedModel: string;
  loading?: boolean;
  initialJdText?: string;
  jdId?: string;
  showCompletenessWarning?: boolean;
  sourceUrl?: string | null;
}

const MAX_JD = 10_000;

export function JDInput({
  onSubmit,
  selectedProvider,
  selectedModel,
  loading,
  initialJdText = "",
  jdId,
  showCompletenessWarning = false,
  sourceUrl,
}: Props) {
  const [jdText, setJdText] = useState(initialJdText);
  const [jdUrl, setJdUrl] = useState(sourceUrl ?? "");
  const [error, setError] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (initialJdText) {
      setJdText(initialJdText);
    }
  }, [initialJdText]);

  useEffect(() => {
    if (sourceUrl) {
      setJdUrl(sourceUrl);
    }
  }, [sourceUrl]);

  const handleSubmit = () => {
    setError(null);
    if (!jdText.trim() && !jdUrl.trim()) {
      setError("Please paste a job description or provide a URL.");
      return;
    }
    if (jdText.length > MAX_JD) {
      setError(`Job description exceeds ${MAX_JD.toLocaleString()} characters. Paste only the requirements section.`);
      return;
    }
    onSubmit({ jd_text: jdText, jd_url: jdUrl || undefined, provider: selectedProvider, model: selectedModel, jd_id: jdId });
  };

  const hostLabel = uncertainJdHostLabel(sourceUrl ?? jdUrl);

  return (
    <div className="space-y-4">
      {showCompletenessWarning && (
        <div className="rounded-xl border border-amber-400/30 bg-amber-400/10 p-4 space-y-3">
          <div className="flex items-start gap-3">
            <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5" />
            <div className="space-y-2 text-sm">
              <p className="text-amber-100 font-medium">
                Review this job description before continuing
              </p>
              <p className="text-amber-100/80 leading-relaxed">
                This posting was auto-captured from the browser extension
                {hostLabel ? ` (${hostLabel})` : ""}. Some job boards and aggregators
                hide parts of the listing or summarize requirements, so sections may be
                missing or reformatted.
              </p>
              <p className="text-amber-100/80 leading-relaxed">
                Scroll through the text below and compare it to the original posting.
                Paste any missing requirements, qualifications, or benefits directly into
                the box before you analyze.
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => {
              textareaRef.current?.focus();
              textareaRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
            }}
            className="text-xs font-semibold text-amber-300 hover:text-amber-200 transition-colors"
          >
            Jump to job description text
          </button>
        </div>
      )}

      <div>
        <label className="block text-slate-400 text-xs mb-1 font-medium">Paste the job description *</label>
        <textarea
          ref={textareaRef}
          value={jdText}
          onChange={(e) => setJdText(e.target.value)}
          placeholder="Paste the full job description here…"
          className="w-full h-64 bg-slate-800 border border-slate-700 rounded-xl p-4 text-slate-200 text-sm resize-none focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600"
        />
        <div className="flex justify-between mt-1">
          <span className={`text-xs ${jdText.length > MAX_JD ? "text-red-400" : "text-slate-500"}`}>
            {jdText.length.toLocaleString()} / {MAX_JD.toLocaleString()}
          </span>
        </div>
      </div>

      <div>
        <label className="block text-slate-400 text-xs mb-1 font-medium">Or provide a job posting URL (optional)</label>
        <input
          value={jdUrl}
          onChange={(e) => setJdUrl(e.target.value)}
          placeholder="https://jobs.example.com/ml-engineer"
          className="w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 text-sm focus:outline-none focus:ring-2 focus:ring-amber-400 placeholder-slate-600"
        />
        <p className="text-slate-600 text-xs mt-1">Note: many job boards require login — pasting the text is more reliable.</p>
      </div>

      {error && (
        <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3">
          <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
          {error}
        </div>
      )}

      <button
        onClick={handleSubmit}
        disabled={loading || (!jdText.trim() && !jdUrl.trim())}
        className="w-full py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 disabled:opacity-40 transition-colors"
      >
        {loading ? "Saving…" : "Analyze job description →"}
      </button>
    </div>
  );
}
