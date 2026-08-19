"use client";

import { useCallback, useEffect, useState } from "react";
import { Download, File, FileText, Loader2, X } from "lucide-react";
import {
  coverLetterExportUrl,
  fetchCoverLetter,
  streamCoverLetterGeneration,
  type CoverLetterOutput,
  type CoverLetterTone,
} from "@/lib/api";
import { cn } from "@/lib/utils";

interface Props {
  sessionId: string;
  accessToken?: string;
  initial?: CoverLetterOutput | null;
  open: boolean;
  onClose: () => void;
}

const TONES: { value: CoverLetterTone; label: string; hint: string }[] = [
  { value: "formal", label: "Formal", hint: "Polished and conservative" },
  { value: "balanced", label: "Balanced", hint: "Professional but personable" },
  { value: "warm", label: "Warm", hint: "Conversational and approachable" },
];

export function CoverLetterPanel({ sessionId, accessToken, initial, open, onClose }: Props) {
  const [tone, setTone] = useState<CoverLetterTone>("balanced");
  const [customHook, setCustomHook] = useState("");
  const [letter, setLetter] = useState<CoverLetterOutput | null>(initial ?? null);
  const [generating, setGenerating] = useState(false);
  const [progress, setProgress] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (initial) setLetter(initial);
  }, [initial]);

  useEffect(() => {
    if (!open || letter || !sessionId) return;
    fetchCoverLetter(sessionId)
      .then(setLetter)
      .catch(() => {
        /* no cached letter yet */
      });
  }, [open, sessionId, letter]);

  const handleGenerate = useCallback(async () => {
    if (!accessToken) {
      setError("Sign in to generate a cover letter.");
      return;
    }
    setGenerating(true);
    setError(null);
    setProgress("Starting…");
    try {
      await streamCoverLetterGeneration(
        sessionId,
        { tone, custom_hook: customHook.trim() || undefined },
        accessToken,
        (evt) => {
          if (evt.event === "progress" && evt.message) {
            setProgress(evt.message);
          }
          if (evt.event === "partial" && evt.data) {
            setLetter(evt.data as CoverLetterOutput);
          }
          if (evt.event === "done" && evt.output) {
            setLetter(evt.output as CoverLetterOutput);
            setProgress(null);
          }
          if (evt.event === "error") {
            setError(evt.message ?? "Generation failed.");
          }
        },
      );
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Generation failed.");
    } finally {
      setGenerating(false);
      setProgress(null);
    }
  }, [accessToken, customHook, sessionId, tone]);

  if (!open) return null;

  const btnCls =
    "flex items-center gap-2 px-3 py-2 rounded-lg font-semibold text-sm transition-colors disabled:opacity-40";

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <button
        type="button"
        className="absolute inset-0 bg-black/50"
        aria-label="Close cover letter panel"
        onClick={onClose}
      />
      <aside className="relative w-full max-w-lg bg-white dark:bg-slate-900 border-l border-slate-300 dark:border-slate-700 h-full overflow-y-auto shadow-2xl">
        <div className="sticky top-0 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 px-6 py-4 flex items-center justify-between z-10">
          <div>
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">Cover letter</h2>
            <p className="text-slate-600 dark:text-slate-400 text-sm">Tailored to your resume and this JD</p>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-2 rounded-lg text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
            aria-label="Close"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        <div className="px-6 py-5 space-y-6">
          <fieldset>
            <legend className="text-sm font-semibold text-slate-700 dark:text-slate-300 mb-3">Tone</legend>
            <div className="space-y-2">
              {TONES.map((t) => (
                <label
                  key={t.value}
                  className={cn(
                    "flex items-start gap-3 p-3 rounded-lg border cursor-pointer transition-colors",
                    tone === t.value
                      ? "border-amber-400/60 bg-amber-500/10 dark:bg-amber-400/10"
                      : "border-slate-300 dark:border-slate-700 hover:border-slate-600",
                  )}
                >
                  <input
                    type="radio"
                    name="cover-letter-tone"
                    value={t.value}
                    checked={tone === t.value}
                    onChange={() => setTone(t.value)}
                    className="mt-1"
                    disabled={generating}
                  />
                  <span>
                    <span className="block text-sm font-medium text-slate-900 dark:text-white">{t.label}</span>
                    <span className="block text-xs text-slate-600 dark:text-slate-400">{t.hint}</span>
                  </span>
                </label>
              ))}
            </div>
          </fieldset>

          <div>
            <label htmlFor="custom-hook" className="block text-sm font-semibold text-slate-700 dark:text-slate-300 mb-2">
              Custom hook <span className="text-slate-600 dark:text-slate-400 font-normal">(optional)</span>
            </label>
            <input
              id="custom-hook"
              type="text"
              value={customHook}
              onChange={(e) => setCustomHook(e.target.value)}
              placeholder="e.g. Your team's work on real-time ML pipelines caught my eye…"
              disabled={generating}
              className="w-full px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-sm text-slate-900 dark:text-white placeholder:text-slate-500 focus:outline-none focus:border-amber-400/50"
            />
          </div>

          {error && (
            <div className="text-sm text-red-700 dark:text-red-400 bg-red-400/10 border border-red-400/20 rounded-lg p-3">
              {error}
            </div>
          )}

          <button
            type="button"
            onClick={handleGenerate}
            disabled={generating}
            className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 disabled:opacity-50"
          >
            {generating ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                {progress ?? "Generating…"}
              </>
            ) : letter ? (
              "Regenerate"
            ) : (
              "Generate"
            )}
          </button>

          {letter && (
            <div className="space-y-4">
              <div className="flex items-center justify-between text-xs text-slate-600 dark:text-slate-400">
                <span>{letter.word_count} words · {letter.tone} tone</span>
                {letter.keywords_used.length > 0 && (
                  <span>{letter.keywords_used.length} JD keywords used</span>
                )}
              </div>
              <textarea
                readOnly
                value={letter.body_plain}
                rows={16}
                className="w-full px-3 py-3 rounded-lg bg-slate-50 dark:bg-slate-950 border border-slate-200 dark:border-slate-800 text-sm text-slate-800 dark:text-slate-200 leading-relaxed resize-none focus:outline-none"
              />
              <div className="flex flex-wrap gap-2">
                <a
                  href={coverLetterExportUrl(sessionId, "pdf")}
                  download="cover_letter.pdf"
                  className={cn(btnCls, "bg-amber-400 text-slate-900 hover:bg-amber-300")}
                >
                  <Download className="w-4 h-4" />
                  PDF
                </a>
                <a
                  href={coverLetterExportUrl(sessionId, "docx")}
                  download="cover_letter.docx"
                  className={cn(btnCls, "bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600")}
                >
                  <File className="w-4 h-4" />
                  DOCX
                </a>
                <a
                  href={coverLetterExportUrl(sessionId, "txt")}
                  download="cover_letter.txt"
                  className={cn(btnCls, "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700")}
                >
                  <FileText className="w-4 h-4" />
                  TXT
                </a>
              </div>
            </div>
          )}
        </div>
      </aside>
    </div>
  );
}
