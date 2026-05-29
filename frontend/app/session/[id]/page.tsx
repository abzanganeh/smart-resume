"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSSE } from "@/lib/sse";
import { triggerPhase, phaseEventsUrl, checkSession } from "@/lib/api";
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
import { ProgressLog } from "@/components/session/ProgressLog";
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

  const [keywords, setKeywords] = useState<KeywordExtractionOutput | null>(null);
  const [audit, setAudit] = useState<AuditOutput | null>(null);
  const [tailored, setTailored] = useState<TailoredResumeOutput | null>(null);
  const [qa, setQa] = useState<QAOutput | null>(null);
  const [costInfo, setCostInfo] = useState<{ cost_formatted: string; provider: string; model: string } | null>(null);
  const [resumeVersion, setResumeVersion] = useState(0);
  const [originalResume, setOriginalResume] = useState("");
  const [runError, setRunError] = useState<string | null>(null);
  const [expiryWarning, setExpiryWarning] = useState(false);
  const [phaseRunning, setPhaseRunning] = useState(false);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [sessionLoaded, setSessionLoaded] = useState(false);

  const runInFlightRef = useRef(false);
  const autoRunForStepRef = useRef<Step | null>(null);

  const { connect, reset, lastEvent, isConnected, isDone } = useSSE();

  const applyPhaseOutput = useCallback((s: Step, output: unknown) => {
    if (s === "audit") {
      const o = output as Record<string, unknown>;
      if (!o || typeof o.overall_score !== "number" || !o.keyword_coverage) {
        return;
      }
      setAudit(output as AuditOutput);
      return;
    }
    if (s === "keywords") {
      const k = output as KeywordExtractionOutput;
      if (!k.must_have_keywords?.length && !k.nice_to_have_keywords?.length) {
        return;
      }
      setKeywords(k);
      return;
    }
    if (s === "rewrite") {
      setTailored(output as TailoredResumeOutput);
      setResumeVersion((v) => v + 1);
    }
    if (s === "export") setQa(output as QAOutput);
  }, []);

  const goTo = (s: Step) => {
    setStep(s);
    router.replace(`/session/${sessionId}?step=${s}`);
  };

  const runCurrentPhase = useCallback(async (options?: { force?: boolean }) => {
    if (runInFlightRef.current) return;
    runInFlightRef.current = true;

    const phase = PHASE_FOR_STEP[step];
    setRunError(null);
    setPhaseRunning(true);
    if (options?.force) {
      if (step === "keywords") setKeywords(null);
      if (step === "audit") setAudit(null);
      if (step === "rewrite") setTailored(null);
      if (step === "export") setQa(null);
      autoRunForStepRef.current = null;
    }
    setProgressLog([]);
    reset();

    try {
      await triggerPhase(sessionId, phase, { force: options?.force });
      connect(phaseEventsUrl(sessionId, phase));
    } catch (e: unknown) {
      setPhaseRunning(false);
      runInFlightRef.current = false;
      autoRunForStepRef.current = null;
      setRunError(e instanceof Error ? e.message : "Failed to start phase.");
    }
  }, [sessionId, step, connect, reset]);

  useEffect(() => {
    if (!lastEvent) return;

    const activePhase = PHASE_FOR_STEP[step];
    if (lastEvent.phase !== undefined && lastEvent.phase !== activePhase) {
      return;
    }

    if (lastEvent.event === "progress" && lastEvent.message) {
      setProgressLog((prev) => [...prev, lastEvent.message!]);
    }

    if (lastEvent.event === "partial" && lastEvent.data) {
      applyPhaseOutput(step, lastEvent.data);
    }

    if (lastEvent.event === "cost_estimate" && lastEvent.cost_formatted) {
      setCostInfo({
        cost_formatted: lastEvent.cost_formatted,
        provider: lastEvent.provider!,
        model: lastEvent.model!,
      });
    }

    if (lastEvent.event === "done") {
      setPhaseRunning(false);
      runInFlightRef.current = false;
      applyPhaseOutput(step, lastEvent.output);
    }
    if (lastEvent.event === "error") {
      setPhaseRunning(false);
      runInFlightRef.current = false;
      autoRunForStepRef.current = null;
      setRunError(lastEvent.message ?? "Phase failed.");
    }
  }, [lastEvent, step, applyPhaseOutput]);

  useEffect(() => {
    let cancelled = false;
    setSessionLoaded(false);

    checkSession(sessionId).then((s) => {
      if (cancelled) return;
      if (s.resume_raw) setOriginalResume(s.resume_raw);

      const phaseNum = String(PHASE_FOR_STEP[step]);
      const cached = s.phases?.[phaseNum];
      if (cached?.status === "done" && cached.output) {
        const hollowKeywords =
          step === "keywords" &&
          !(cached.output as KeywordExtractionOutput).must_have_keywords?.length &&
          !(cached.output as KeywordExtractionOutput).nice_to_have_keywords?.length;
        if (!hollowKeywords) {
          applyPhaseOutput(step, cached.output);
        }
      }
      setSessionLoaded(true);
    }).catch(() => {
      if (!cancelled) setSessionLoaded(true);
    });

    return () => { cancelled = true; };
  }, [sessionId, step, applyPhaseOutput]);

  useEffect(() => {
    runInFlightRef.current = false;
    autoRunForStepRef.current = null;
    setPhaseRunning(false);
    setProgressLog([]);
    setRunError(null);
    reset();
  }, [step, reset]);

  useEffect(() => {
    if (!sessionLoaded) return;

    const hasOutput = {
      keywords: !!keywords,
      audit: !!audit,
      rewrite: !!tailored,
      export: !!qa,
    }[step];

    if (hasOutput || runInFlightRef.current) return;
    if (autoRunForStepRef.current === step) return;

    autoRunForStepRef.current = step;
    runCurrentPhase();
  }, [sessionLoaded, step, keywords, audit, tailored, qa, runCurrentPhase]);

  useEffect(() => {
    const timer = setTimeout(() => setExpiryWarning(true), 20 * 60 * 60 * 1000);
    return () => clearTimeout(timer);
  }, []);

  const stepIndex = STEPS.indexOf(step);
  const isStreaming = phaseRunning || (isConnected && !isDone);
  const showProgress = phaseRunning;

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {expiryWarning && (
        <div className="bg-amber-400/10 border-b border-amber-400/30 px-6 py-2 text-center text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />
          Your session expires in 4 hours. Download your resume before it's gone.
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-10">
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

        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          {runError && (
            <div className="flex items-start gap-2 text-red-400 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3 mb-6">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0" />
              {runError}
              <button onClick={() => { setRunError(null); runCurrentPhase({ force: true }); }} className="ml-auto underline hover:no-underline">Retry</button>
            </div>
          )}

          {step === "keywords" && (
            <div>
              <h1 className="text-xl font-bold mb-1">JD Keyword Analysis</h1>
              <p className="text-slate-400 text-sm mb-4">Every ATS keyword the recruiter is looking for, extracted and explained.</p>
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              <KeywordDashboard output={keywords} streaming={isStreaming && !showProgress} />
              {keywords && !isStreaming && (
                <button onClick={() => goTo("audit")} className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors">
                  Audit my resume →
                </button>
              )}
              {!keywords && !isStreaming && sessionLoaded && (
                <div className="mt-6 flex items-center gap-3">
                  <p className="text-amber-400 text-sm">No keywords were extracted. Try again or switch to a stronger model (e.g. gpt-4o).</p>
                  <button
                    type="button"
                    onClick={() => runCurrentPhase({ force: true })}
                    className="px-4 py-2 rounded-lg bg-slate-700 hover:bg-slate-600 text-sm font-medium"
                  >
                    Retry
                  </button>
                </div>
              )}
            </div>
          )}

          {step === "audit" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Resume Audit</h1>
              <p className="text-slate-400 text-sm mb-4">Every gap, weak bullet, and cliché — flagged before the rewrite.</p>
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              <AuditPanel
                output={audit}
                streaming={isStreaming && !showProgress}
                sessionId={sessionId}
                onReaudit={() => runCurrentPhase({ force: true })}
              />
              {audit && !isStreaming && (
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
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              {tailored && (
                <div className="mb-4">
                  <VersionHistory sessionId={sessionId} currentVersion={resumeVersion} onRestore={() => {}} />
                </div>
              )}
              <ResumeDiff
                tailored={tailored}
                streaming={isStreaming && !showProgress}
                costInfo={costInfo}
                sessionId={sessionId}
                onEdited={(updated) => setTailored(updated)}
              />
              {tailored && !isStreaming && (
                <button onClick={() => goTo("export")} className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors">
                  Run QA & export →
                </button>
              )}
            </div>
          )}

          {step === "export" && (
            <div>
              <h1 className="text-xl font-bold mb-1">QA & Export</h1>
              <p className="text-slate-400 text-sm mb-4">Final quality check before you download.</p>
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              <QAChecklist output={qa} streaming={isStreaming && !showProgress} />
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
