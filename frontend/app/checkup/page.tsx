"use client";

import { useCallback, useRef, useState } from "react";
import Link from "next/link";
import {
  AlertCircle,
  ArrowRight,
  Briefcase,
  FileText,
  Loader2,
  Sparkles,
  Upload,
} from "lucide-react";
import { ATSGuidancePanel } from "@/components/session/ATSGuidancePanel";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { runCheckup, type QAOutput } from "@/lib/api";
import { saveCheckupHandoff } from "@/lib/checkupHandoff";
import { clsx } from "clsx";

type ResumeTab = "paste" | "upload";

const MAX_JD = 10_000;
const MAX_RESUME = 50_000;

export default function CheckupPage() {
  const [resumeTab, setResumeTab] = useState<ResumeTab>("paste");
  const [resumeText, setResumeText] = useState("");
  const [resumeFile, setResumeFile] = useState<File | null>(null);
  const [jobTitle, setJobTitle] = useState("");
  const [jdText, setJdText] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<QAOutput | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const canSubmit =
    jdText.trim().length >= 20 &&
    (resumeText.trim().length > 0 || resumeFile !== null) &&
    !loading;

  const handleAnalyze = useCallback(async () => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);
    try {
      const qa = await runCheckup({
        jdText,
        jobTitle,
        resumeText: resumeTab === "paste" ? resumeText : undefined,
        file: resumeTab === "upload" ? resumeFile : null,
      });
      setResult(qa);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Checkup failed. Try again.");
    } finally {
      setLoading(false);
    }
  }, [canSubmit, jdText, jobTitle, resumeTab, resumeText, resumeFile]);

  const handleCreateAccount = useCallback(() => {
    saveCheckupHandoff({
      resumeText: resumeTab === "paste" ? resumeText : "",
      jdText,
      jobTitle,
    });
  }, [jdText, jobTitle, resumeTab, resumeText]);

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white">
      <header className="border-b border-slate-800 bg-slate-950/60">
        <div className="max-w-5xl mx-auto px-6 py-4 flex items-center justify-between gap-4">
          <Link href="/" className="shrink-0">
            <BrandLogo className="h-8 w-auto" />
          </Link>
          <div className="flex items-center gap-3 text-sm">
            <Link href="/auth" className="text-slate-400 hover:text-white transition-colors">
              Sign in
            </Link>
            <Link
              href="/auth?mode=register"
              className="px-3 py-1.5 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 transition-colors"
            >
              Register free
            </Link>
          </div>
        </div>
      </header>

      <div className="max-w-5xl mx-auto px-6 py-10 space-y-8">
        <div className="text-center max-w-2xl mx-auto">
          <div className="inline-flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-300 mb-4">
            <Sparkles className="w-4 h-4 text-amber-400" />
            Free ATS check — no account required
          </div>
          <h1 className="text-3xl font-bold tracking-tight mb-3">Resume checkup</h1>
          <p className="text-slate-400 text-sm leading-relaxed">
            Paste your resume and a job description to get an instant ATS-style score,
            issue breakdown, and quick wins. No signup, no paywall.
          </p>
        </div>

        <div className="grid lg:grid-cols-2 gap-6">
          <section className="rounded-xl border border-slate-700 bg-slate-800/50 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <FileText className="w-4 h-4 text-amber-400" />
              Your resume
            </h2>
            <div className="flex gap-2">
              {(["paste", "upload"] as const).map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setResumeTab(tab)}
                  className={clsx(
                    "px-3 py-1.5 rounded-lg text-xs font-medium border transition-colors",
                    resumeTab === tab
                      ? "bg-amber-400/15 border-amber-400/40 text-amber-200"
                      : "border-slate-700 text-slate-400 hover:border-slate-600",
                  )}
                >
                  {tab === "paste" ? "Paste text" : "Upload file"}
                </button>
              ))}
            </div>
            {resumeTab === "paste" ? (
              <textarea
                value={resumeText}
                onChange={(e) => setResumeText(e.target.value.slice(0, MAX_RESUME))}
                placeholder="Paste your resume text here..."
                rows={12}
                className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-amber-400/50 resize-y"
              />
            ) : (
              <div className="space-y-3">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.docx,.txt,application/pdf,application/vnd.openxmlformats-officedocument.wordprocessingml.document,text/plain"
                  className="hidden"
                  onChange={(e) => setResumeFile(e.target.files?.[0] ?? null)}
                />
                <button
                  type="button"
                  onClick={() => fileInputRef.current?.click()}
                  className="w-full flex flex-col items-center gap-2 py-8 rounded-lg border border-dashed border-slate-600 hover:border-amber-400/40 text-slate-400 hover:text-slate-200 transition-colors"
                >
                  <Upload className="w-6 h-6" />
                  <span className="text-sm">
                    {resumeFile ? resumeFile.name : "PDF, DOCX, or TXT"}
                  </span>
                </button>
              </div>
            )}
          </section>

          <section className="rounded-xl border border-slate-700 bg-slate-800/50 p-5 space-y-4">
            <h2 className="text-sm font-semibold text-slate-200 flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-amber-400" />
              Target job
            </h2>
            <input
              type="text"
              value={jobTitle}
              onChange={(e) => setJobTitle(e.target.value)}
              placeholder="Job title (optional)"
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-amber-400/50"
            />
            <textarea
              value={jdText}
              onChange={(e) => setJdText(e.target.value.slice(0, MAX_JD))}
              placeholder="Paste the full job description (at least 20 characters)..."
              rows={14}
              className="w-full rounded-lg bg-slate-900 border border-slate-700 px-3 py-2 text-sm text-slate-200 placeholder:text-slate-600 focus:outline-none focus:border-amber-400/50 resize-y"
            />
            <p className="text-xs text-slate-500">{jdText.length.toLocaleString()} / {MAX_JD.toLocaleString()} chars</p>
          </section>
        </div>

        {error && (
          <p className="text-red-400 text-sm flex items-center gap-2 justify-center">
            <AlertCircle className="w-4 h-4 shrink-0" />
            {error}
          </p>
        )}

        <div className="flex justify-center">
          <button
            type="button"
            onClick={handleAnalyze}
            disabled={!canSubmit}
            className="inline-flex items-center gap-2 px-6 py-3 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
          >
            {loading ? <Loader2 className="w-5 h-5 animate-spin" /> : <Sparkles className="w-5 h-5" />}
            Run checkup
          </button>
        </div>

        {result && (
          <div className="space-y-6">
            <ATSGuidancePanel output={result} variant="primary" />
            <div className="rounded-xl border border-amber-400/30 bg-amber-400/5 p-6 text-center space-y-3">
              <p className="text-slate-200 text-sm">
                Want AI to fix these issues and export a tailored resume?
              </p>
              <Link
                href="/auth?mode=register&callbackUrl=/session/new?from=checkup&step=jd"
                onClick={handleCreateAccount}
                className="inline-flex items-center gap-2 px-5 py-2.5 rounded-lg bg-amber-400 text-slate-900 font-semibold hover:bg-amber-300 transition-colors"
              >
                Create a free account to fix with AI
                <ArrowRight className="w-4 h-4" />
              </Link>
              <p className="text-xs text-slate-500">6 credits on signup · No credit card</p>
            </div>
          </div>
        )}
      </div>
    </main>
  );
}
