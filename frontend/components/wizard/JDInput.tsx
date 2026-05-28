"use client";

import { useState } from "react";
import { AlertCircle } from "lucide-react";
import { type JDPayload } from "@/lib/api";

interface Props {
  onSubmit: (payload: JDPayload) => void;
  selectedProvider: string;
  selectedModel: string;
  loading?: boolean;
}

const MAX_JD = 10_000;

export function JDInput({ onSubmit, selectedProvider, selectedModel, loading }: Props) {
  const [jdText, setJdText] = useState("");
  const [jdUrl, setJdUrl] = useState("");
  const [error, setError] = useState<string | null>(null);

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
    onSubmit({ jd_text: jdText, jd_url: jdUrl || undefined, provider: selectedProvider, model: selectedModel });
  };

  return (
    <div className="space-y-4">
      <div>
        <label className="block text-slate-400 text-xs mb-1 font-medium">Paste the job description *</label>
        <textarea
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
