"use client";

import { Suspense, useEffect, useState, useCallback } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSSE, type SSEEvent } from "@/lib/sse";
import { triggerPhase, phaseEventsUrl } from "@/lib/api";
import {
  type KeywordExtractionOutput,
  type AuditOutput,
  type TailoredResumeOutput,
  type QAOutput,
} from "@/lib/api";
import { KeywordDashboard } from "@/components/session/KeywordDashboard";
import { AuditPanel } from "@/components/session/AuditPanel";
import { ResumeDiff } from "@/components/session/ResumeDiff";
import { QAChecklist } from "@/components/session/QAChecklist";
import { ExportButtons } from "@/components/session/ExportButtons";
import { VersionHistory } from "@/components/session/VersionHistory";
import { AlertCircle, ChevronRight } from "lucide-react";

type Step = "keywords" | "audit" | "rewrite" | "export";

const PHASE_FOR_STEP: Record<Step, number> = { keywords: 1, audit: 2, rewrite: 3, export: 4 };
const STEPS: Step[] = ["keywords", "audit", "rewrite", "export"];
const STEP_LABELS: Record<Step, string> = { keywords: "JD Keywords", audit: "Resume Audit", rewrite: "Tailored Rewrite", export: "QA & Export" };

function SessionContent() {
  const { id: sessionId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState<Step>((searchParams.get("step") as Step) ?? "keywords");

  // Phase outputs
  const [keywords, setKeywords] = useState<KeywordExtractionOutput | null>(null);
  const [audit, setAudit] = useState<AuditOutput | null>(null);
  const [tailored, setTailored] = useState<TailoredResumeOutput | null>(null);
  const [qa, setQa] = useState<QAOutput | null>(null);
  const [costInfo, setCostInfo] = useState<{ cost_formatted: string; provider: string; model: string } | null>(null);
  const [resumeVersion, setResumeVersion] = useState(0);
  const [originalResume, setOriginalResume] = useState("");
  const [runError, setRunError] = useState<string | null>(null);
  const [expiryWarning, setExpiryWarning] = useState(false);

  const sse = useSSE();

  const goTo = (s: Step) => {
    setStep(s);
    router.replace(`/session/${sessionId}?step=${s}`);
  };

  // Trigger the current step's phase
  const runCurrentPhase = useCallback(async () => {
    const phase = PHASE_FOR_STEP[step];
    setRunError(null);
    try {
      await triggerPhase(sessionId, phase);
      const url = phaseEventsUrl(sessionId, phase);
      sse.connect(url);
    } catch (e: unknown) {
      setRunError(e instanceof Error ? e.message : "Failed to start phase.");
    }
  }, [sessionId, step]);

  // Process SSE events
  useEffect(() => {
    const last = sse.lastEvent;
    if (!last) return;

    if (last.event === "cost_estimate" && last.cost_formatted) {
      setCostInfo({ cost_formatted: last.cost_formatted, provider: last.provider!, model: last.model! });
    }

    if (last.event === "done") {
      const output = last.output as Record<string, unknown>;
      if (step === "keywords") setKeywords(output as unknown as KeywordExtractionOutput);
      if (step === "audit") setAudit(output as unknown as AuditOutput);
      if (step === "rewrite") { setTailored(output as unknown as TailoredResumeOutput); setResumeVersion((v) => v + 1); }
      if (step === "export") setQa(output as unknown as QAOutput);
    }
    if (last.event === "error") {
      setRunError(last.message ?? "Phase failed.");
    }
  }, [sse.lastEvent, step]);

  // Auto-run phase on step load
  useEffect(() => {
    // Only run if no output yet for this step
    const hasOutput = {
      keywords: !!keywords,
      audit: !!audit,
      rewrite: !!tailored,
      export: !!qa,
    }[step];

    if (!hasOutput && !sse.isConnected) {
      runCurrentPhase();
    }
  }, [step]);

  // Session expiry check (20h warning)
  useEffect(() => {
    const timer = setTimeout(() => setExpiryWarning(true), 20 * 60 * 60 * 1000);
    return () => clearTimeout(timer);
  }, []);

  const stepIndex = STEPS.indexOf(step);
  const currentPhaseOutput = { keywords, audit, rewrite: tailored, export: qa }[step];
  const isStreaming = sse.isConnected && !sse.isDone;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {/* Expiry banner */}
      {expiryWarning && (
        <div className="bg-amber-400/10 border-b border-amber-400/30 px-6 py-2 text-center text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />
          Your session expires in 4 hours. Download your resume before it's gone.
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-10">
        {/* Step navigation */}
        <div className="flex items-center gap-1 mb-8 overflow-x-auto pb-2">
          {STEPS.map((s, i) => {
            const done = i < stepIndex || !!({ keywords, audit, rewrite: tailored, export: qa }[s]);
            const active = s === step;
            return (
              <div key={s} className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => i <= stepIndex && goTo(s)}
                  disabled={i > stepIndex}
                  className={`px-4 py-1.5 rounded-full text-sm font-medium transition-colors
                    ${active ? "bg-amber-400 text-slate-900" : done ? "bg-slate-700 text-slate-200 hover:bg-slate-600" : "bg-slate-800 text-slate-500 cursor-not-allowed"}`}
                >
                  {STEP_LABELS[s]}
                </button>
                {i < STEPS.length - 1 && <ChevronRight className="w-4 h-4 text-slate-700" />}
              </div>
            );
          })}
        </div>

        {/* Content */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          {/* Error */}
          {runError && (
            <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3 mb-6">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              {runError}
              <button onClick={runCurrentPhase} className="ml-auto underline hover:no-underline">Retry</button>
            </div>
          )}

          {step === "keywords" && (
            <div>
              <h1 className="text-xl font-bold mb-1">JD Keyword Analysis</h1>
              <p className="text-slate-400 text-sm mb-6">Every ATS keyword the recruiter is looking for, extracted and explained.</p>
              <KeywordDashboard output={keywords} streaming={isStreaming} />
              {keywords && (
                <button onClick={() => goTo("audit")} className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors">
                  Audit my resume →
                </button>
              )}
            </div>
          )}

          {step === "audit" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Resume Audit</h1>
              <p className="text-slate-400 text-sm mb-6">Every gap, weak bullet, and cliché — flagged before the rewrite.</p>
              <AuditPanel output={audit} streaming={isStreaming} />
              {audit && (
                <button onClick={() => goTo("rewrite")} className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors">
                  Rewrite my resume →
                </button>
              )}
            </div>
          )}

          {step === "rewrite" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Tailored Rewrite</h1>
              <p className="text-slate-400 text-sm mb-4">Your resume, rewritten with exact JD phrasing and quality rules applied.</p>
              {tailored && (
                <div className="mb-4">
                  <VersionHistory sessionId={sessionId} currentVersion={resumeVersion} onRestore={() => {}} />
                </div>
              )}
              <ResumeDiff original={originalResume} tailored={tailored} streaming={isStreaming} costInfo={costInfo} />
              {tailored && (
                <button onClick={() => goTo("export")} className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors">
                  Run QA & export →
                </button>
              )}
            </div>
          )}

          {step === "export" && (
            <div>
              <h1 className="text-xl font-bold mb-1">QA & Export</h1>
              <p className="text-slate-400 text-sm mb-6">Final quality check before you download.</p>
              <QAChecklist output={qa} streaming={isStreaming} />
              {qa && (
                <div className="mt-6">
                  <h2 className="text-slate-300 font-semibold mb-3 text-sm">Download your tailored resume</h2>
                  <ExportButtons sessionId={sessionId} disabled={false} />
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function SessionPage() {
  return (
    <Suspense fallback={<div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">Loading session…</div>}>
      <SessionContent />
    </Suspense>
  );
}
