"use client";

import { Suspense, useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSSE } from "@/lib/sse";
import {
  triggerPhase,
  phaseEventsUrl,
  checkSession,
  getLLMUpgradeStatus,
  createLLMUpgradeCheckout,
  ApiError,
  type PhaseRunScope,
  type KeywordExtractionOutput,
  type AuditOutput,
  type TailoredResumeOutput,
  type QAOutput,
  type CoverLetterOutput,
  type LLMTier,
  type LLMUpgradeStatus,
  type LLMUpgradeCheckoutCode,
} from "@/lib/api";
import { trackRecentSession } from "@/lib/recentSessions";
import { useSession } from "next-auth/react";
import { KeywordDashboard } from "@/components/session/KeywordDashboard";
import { AuditPanel } from "@/components/session/AuditPanel";
import { ResumeDiff } from "@/components/session/ResumeDiff";
import { QAChecklist } from "@/components/session/QAChecklist";
import { ATSGuidancePanel } from "@/components/session/ATSGuidancePanel";
import { ExportButtons } from "@/components/session/ExportButtons";
import { CoverLetterPanel } from "@/components/session/CoverLetterPanel";
import { VersionHistory } from "@/components/session/VersionHistory";
import { ProgressLog } from "@/components/session/ProgressLog";
import { StaleBanner } from "@/components/session/StaleBanner";
import {
  LLMTierSelector,
  LLMUpgradePurchaseModal,
} from "@/components/session/LLMTierSelector";
import { AlertCircle, ChevronRight } from "lucide-react";

type Step = "keywords" | "audit" | "rewrite" | "export";

const PHASE_FOR_STEP: Record<Step, number> = { keywords: 1, audit: 2, rewrite: 3, export: 4 };
const STEPS: Step[] = ["keywords", "audit", "rewrite", "export"];
const STEP_LABELS: Record<Step, string> = {
  keywords: "JD Keywords",
  audit: "Resume Audit",
  rewrite: "Tailored Rewrite",
  export: "QA & Export",
};

function SessionContent() {
  const { id: sessionId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState<Step>((searchParams.get("step") as Step) ?? "keywords");

  const [keywords, setKeywords] = useState<KeywordExtractionOutput | null>(null);
  const [audit, setAudit] = useState<AuditOutput | null>(null);
  const [tailored, setTailored] = useState<TailoredResumeOutput | null>(null);
  const [qa, setQa] = useState<QAOutput | null>(null);
  // Fix 2: hydrate claimed keywords / extra notes / bullet fixes from session on load.
  const [sessionClaimedKeywords, setSessionClaimedKeywords] = useState<string[]>([]);
  const [sessionExtraNotes, setSessionExtraNotes] = useState("");
  const [sessionBulletFixes, setSessionBulletFixes] = useState<import("@/lib/api").BulletFixPayload[]>([]);
  const [costInfo, setCostInfo] = useState<{ cost_formatted: string; provider: string; model: string } | null>(null);
  const [resumeVersion, setResumeVersion] = useState(0);
  const [runError, setRunError] = useState<string | null>(null);
  const [runErrorCode, setRunErrorCode] = useState<string | null>(null);
  const [expiryWarning, setExpiryWarning] = useState(false);
  const [phaseRunning, setPhaseRunning] = useState(false);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [phase1Complete, setPhase1Complete] = useState(false);
  const [stale, setStale] = useState<Record<string, string | null>>({ "3": null, "4": null });
  const [atsScoreHistory, setAtsScoreHistory] = useState<number[]>([]);
  const [appliedSuggestion, setAppliedSuggestion] = useState<string | null>(null);
  const [phase4RecalcActive, setPhase4RecalcActive] = useState(false);
  const [atsRecalcRunning, setAtsRecalcRunning] = useState(false);
  const [coverLetterOpen, setCoverLetterOpen] = useState(false);
  const [coverLetter, setCoverLetter] = useState<CoverLetterOutput | null>(null);

  const [llmTier, setLlmTier] = useState<LLMTier>("standard");
  const [llmStatus, setLlmStatus] = useState<LLMUpgradeStatus | null>(null);
  const [purchaseTier, setPurchaseTier] = useState<Exclude<LLMTier, "standard"> | null>(null);
  const [checkoutBusyCode, setCheckoutBusyCode] = useState<LLMUpgradeCheckoutCode | null>(null);

  const { data: authSession } = useSession();
  const runInFlightRef = useRef(false);
  const activeStepRef = useRef<Step>(step);
  const phase4RecalcRef = useRef(false);
  const tailoredBackupRef = useRef<TailoredResumeOutput | null>(null);

  const { connect, reset, lastEvent, isConnected, isDone } = useSSE();

  useEffect(() => {
    activeStepRef.current = step;
  }, [step]);

  useEffect(() => {
    phase4RecalcRef.current = phase4RecalcActive;
  }, [phase4RecalcActive]);

  // Keep a backup of the latest tailored state so we can restore it if Phase 3 fails.
  useEffect(() => {
    if (tailored !== null) {
      tailoredBackupRef.current = tailored;
    }
  }, [tailored]);

  const recordAtsScore = useCallback((qaOut: QAOutput) => {
    if (typeof qaOut.ats_score === "number") {
      setAtsScoreHistory((prev) => [...prev.slice(-4), qaOut.ats_score!]);
    }
  }, []);

  const applyPhaseOutput = useCallback((s: Step, output: unknown) => {
    if (s === "audit") {
      const o = output as Record<string, unknown>;
      if (!o || typeof o.overall_score !== "number" || !o.keyword_coverage) return;
      setAudit(output as AuditOutput);
      return;
    }
    if (s === "keywords") {
      const k = output as KeywordExtractionOutput;
      if (!k.must_have_keywords?.length && !k.nice_to_have_keywords?.length) return;
      setKeywords(k);
      return;
    }
    if (s === "rewrite") {
      setTailored(output as TailoredResumeOutput);
      setResumeVersion((v) => v + 1);
    }
    if (s === "export") {
      const qaOut = output as QAOutput;
      setQa(qaOut);
      recordAtsScore(qaOut);
    }
  }, [recordAtsScore]);

  const hydrateFromSession = useCallback((s: Awaited<ReturnType<typeof checkSession>>) => {
    setStale(s.stale ?? { "3": null, "4": null });
    setPhase1Complete(!!s.phase1_complete);

    const applyCached = (stepKey: Step, phaseNum: string) => {
      const cached = s.phases?.[phaseNum];
      if (cached?.status === "done" && cached.output) {
        applyPhaseOutput(stepKey, cached.output);
      }
    };
    applyCached("keywords", "1");
    applyCached("audit", "2");
    applyCached("rewrite", "3");
    applyCached("export", "4");

    const phase4 = s.phases?.["4"];
    if (phase4?.status === "done" && phase4.output) {
      const out = phase4.output as QAOutput;
      if (typeof out.ats_score === "number") {
        setAtsScoreHistory([out.ats_score]);
      }
    }
    if (s.cover_letter) {
      setCoverLetter(s.cover_letter);
    }
    // Fix 2: restore user additions so AuditPanel survives a page refresh.
    if (s.user_claimed_keywords?.length) setSessionClaimedKeywords(s.user_claimed_keywords);
    if (s.user_extra_notes) setSessionExtraNotes(s.user_extra_notes);
    if (s.bullet_fixes?.length) setSessionBulletFixes(s.bullet_fixes);
  }, [applyPhaseOutput]);

  const goTo = (s: Step) => {
    setStep(s);
    router.replace(`/session/${sessionId}?step=${s}`);
  };

  const runPhase = useCallback(
    async (targetStep: Step, options?: { force?: boolean; scope?: PhaseRunScope }) => {
      if (runInFlightRef.current) return;
      runInFlightRef.current = true;

      const phase = PHASE_FOR_STEP[targetStep];
      setRunError(null);
      setRunErrorCode(null);
      setPhaseRunning(true);
      if (options?.force) {
        if (targetStep === "keywords") setKeywords(null);
        if (targetStep === "audit") setAudit(null);
        if (targetStep === "rewrite") {
          // Save the current tailored output so we can restore it if Phase 3 fails.
          // setTailored is a state setter, so we read the backup from the ref that
          // mirrors the latest tailored state.
          tailoredBackupRef.current = tailoredBackupRef.current; // already up-to-date via useEffect
          setTailored(null);
        }
        if (targetStep === "export") setQa(null);
      }
      setProgressLog([]);
      reset();

      try {
        await triggerPhase(sessionId, phase, {
          force: options?.force,
          scope: options?.scope,
          llmTier: phase === 3 ? llmTier : undefined,
        });
        connect(phaseEventsUrl(sessionId, phase));
      } catch (e: unknown) {
        setPhaseRunning(false);
        runInFlightRef.current = false;
        setPhase4RecalcActive(false);
        setAtsRecalcRunning(false);
        const errorCode = e instanceof ApiError ? e.code : undefined;
        setRunErrorCode(errorCode ?? null);
        setRunError(e instanceof Error ? e.message : "Failed to start phase.");
        // Restore the tailored resume if Phase 3 failed — don't leave the user with a blank rewrite.
        if (targetStep === "rewrite" && tailoredBackupRef.current) {
          setTailored(tailoredBackupRef.current);
        }
      }
    },
    [sessionId, connect, reset, llmTier]
  );

  const recalculateAts = useCallback(async () => {
    if (runInFlightRef.current) return;
    setPhase4RecalcActive(true);
    setAtsRecalcRunning(true);
    await runPhase("export", { force: true });
  }, [runPhase]);

  const runCurrentPhase = useCallback(
    (options?: { force?: boolean; scope?: PhaseRunScope }) => runPhase(step, options),
    [step, runPhase]
  );

  useEffect(() => {
    if (!lastEvent) return;

    const activePhase = PHASE_FOR_STEP[activeStepRef.current];
    const isPhase4Recalc = phase4RecalcRef.current && lastEvent.phase === 4;

    if (
      lastEvent.phase !== undefined &&
      lastEvent.phase !== activePhase &&
      !isPhase4Recalc
    ) {
      return;
    }

    const outputStep: Step = isPhase4Recalc ? "export" : activeStepRef.current;

    if (lastEvent.event === "progress" && lastEvent.message) {
      setProgressLog((prev) => [...prev, lastEvent.message!]);
    }
    if (lastEvent.event === "partial" && lastEvent.data) {
      applyPhaseOutput(outputStep, lastEvent.data);
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
      applyPhaseOutput(outputStep, lastEvent.output);
      if (lastEvent.phase === 3) {
        setStale((prev) => ({ ...prev, "3": null, "4": null }));
      }
      if (lastEvent.phase === 4) {
        setStale((prev) => ({ ...prev, "4": null }));
        setPhase4RecalcActive(false);
        setAtsRecalcRunning(false);
      }
    }
    if (lastEvent.event === "error") {
      setPhaseRunning(false);
      runInFlightRef.current = false;
      setPhase4RecalcActive(false);
      setAtsRecalcRunning(false);
      setRunError(lastEvent.message ?? "Phase failed.");
    }
  }, [lastEvent, applyPhaseOutput]);

  useEffect(() => {
    let cancelled = false;
    setSessionLoaded(false);
    setAtsScoreHistory([]);
    setAppliedSuggestion(null);

    checkSession(sessionId)
      .then((s) => {
        if (cancelled) return;
        hydrateFromSession(s);
        trackRecentSession(sessionId, s.resume_raw?.slice(0, 40) || undefined);
        setSessionLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setSessionLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, hydrateFromSession]);

  const refreshLLMStatus = useCallback(async () => {
    // Don't call subscription endpoints when token is absent or expired.
    if (!authSession?.backendAccessToken || authSession.error === "TokenExpired") return;
    try {
      const status = await getLLMUpgradeStatus(authSession.backendAccessToken);
      setLlmStatus(status);
      setLlmTier((current) => {
        if (current === "best" && status.best_soft_cap_hit) return "standard";
        if (current === "best" && !status.best_subscription_active) return "standard";
        if (
          current === "better" &&
          !status.better_subscription_active &&
          status.better_credits_balance <= 0
        ) {
          return "standard";
        }
        return current;
      });
    } catch {
      setLlmStatus(null);
    }
  }, [authSession?.backendAccessToken]);

  useEffect(() => {
    void refreshLLMStatus();
  }, [refreshLLMStatus]);

  const handleRequestPurchase = useCallback(
    (tier: Exclude<LLMTier, "standard">) => {
      setPurchaseTier(tier);
    },
    [],
  );

  const handleCheckout = useCallback(
    async (code: LLMUpgradeCheckoutCode) => {
      if (!authSession?.backendAccessToken || authSession.error === "TokenExpired") return;
      setCheckoutBusyCode(code);
      try {
        const origin =
          typeof window !== "undefined" ? window.location.origin : "";
        const ret = `${origin}/session/${sessionId}?step=rewrite&llm_purchase=success`;
        const cancel = `${origin}/session/${sessionId}?step=rewrite&llm_purchase=cancel`;
        const { url } = await createLLMUpgradeCheckout(
          authSession.backendAccessToken,
          { code, success_url: ret, cancel_url: cancel },
        );
        if (typeof window !== "undefined") {
          window.location.assign(url);
        }
      } catch (e) {
        setRunError(
          e instanceof Error ? e.message : "Failed to start checkout.",
        );
        setCheckoutBusyCode(null);
        setPurchaseTier(null);
      }
    },
    [authSession?.backendAccessToken, sessionId],
  );

  useEffect(() => {
    if (!lastEvent) return;
    if (lastEvent.event === "best_soft_cap_hit") {
      void refreshLLMStatus();
      setLlmTier("standard");
    }
    if (lastEvent.event === "tier_downgraded") {
      void refreshLLMStatus();
    }
    if (lastEvent.event === "done" && lastEvent.phase === 3) {
      void refreshLLMStatus();
    }
  }, [lastEvent, refreshLLMStatus]);

  useEffect(() => {
    runInFlightRef.current = false;
    setPhaseRunning(false);
    setProgressLog([]);
    setRunError(null);
    setRunErrorCode(null);
    reset();
  }, [step, reset]);

  useEffect(() => {
    const timer = setTimeout(() => setExpiryWarning(true), 20 * 60 * 60 * 1000);
    return () => clearTimeout(timer);
  }, []);

  const stepHasOutput = {
    keywords: !!keywords,
    audit: !!audit,
    rewrite: !!tailored,
    export: !!qa,
  };

  const tabsUnlocked = phase1Complete;
  const isStreaming = phaseRunning || (isConnected && !isDone);
  const showProgress = phaseRunning;

  const staleMessageForStep = (s: Step): string | null => {
    if (s === "rewrite" && stale["3"]) {
      return "Your audit changed. Re-run Phase 3 to apply updates.";
    }
    if (s === "export" && stale["4"]) {
      return "Your rewrite changed. Re-run Phase 4 to refresh QA.";
    }
    return null;
  };

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      {expiryWarning && (
        <div className="bg-amber-400/10 border-b border-amber-400/30 px-6 py-2 text-center text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />
          Your session expires in 4 hours. Download your resume before it&apos;s gone.
        </div>
      )}

      <div className="max-w-5xl mx-auto px-6 py-10">
        <div className="flex items-center gap-1 mb-8 overflow-x-auto pb-2">
          {STEPS.map((s, i) => {
            const active = s === step;
            const hasOutput = stepHasOutput[s];
            const isStale = (s === "rewrite" && !!stale["3"]) || (s === "export" && !!stale["4"]);
            const clickable = tabsUnlocked;
            return (
              <div key={s} className="flex items-center gap-1 shrink-0">
                <button
                  onClick={() => clickable && goTo(s)}
                  disabled={!clickable}
                  className={`relative px-4 py-1.5 rounded-full text-sm font-medium transition-colors
                    ${active ? "bg-amber-400 text-slate-900" : hasOutput ? "bg-slate-700 text-slate-200 hover:bg-slate-600" : clickable ? "bg-slate-800 text-slate-300 hover:bg-slate-700" : "bg-slate-800 text-slate-500 cursor-not-allowed"}`}
                >
                  {STEP_LABELS[s]}
                  {isStale && (
                    <span
                      className="absolute -top-0.5 -right-0.5 w-2.5 h-2.5 rounded-full bg-amber-400 border-2 border-slate-950"
                      title="Output may be outdated"
                    />
                  )}
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
              {runErrorCode === "master_resume_required" ? (
                <Link
                  href="/profile"
                  className="ml-auto whitespace-nowrap underline hover:no-underline"
                  onClick={() => setRunError(null)}
                >
                  Upload master resume →
                </Link>
              ) : (
                <button
                  onClick={() => {
                    setRunError(null);
                    setRunErrorCode(null);
                    runCurrentPhase({ force: true });
                  }}
                  className="ml-auto underline hover:no-underline"
                >
                  Retry
                </button>
              )}
            </div>
          )}

          {staleMessageForStep(step) && (
            <StaleBanner
              message={staleMessageForStep(step)!}
              onRerun={() => runCurrentPhase({ force: true })}
              running={phaseRunning}
            />
          )}

          {step === "keywords" && (
            <div>
              <div className="flex items-center justify-between mb-4">
                <div>
                  <h1 className="text-xl font-bold mb-1">JD Keyword Analysis</h1>
                  <p className="text-slate-400 text-sm">
                    Every ATS keyword the recruiter is looking for, extracted and explained.
                  </p>
                </div>
                {phase1Complete && (
                  <Link href="/session/new" className="text-xs text-amber-400 hover:text-amber-300 underline">
                    New session
                  </Link>
                )}
              </div>
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              {!keywords && !phaseRunning && sessionLoaded && (
                <button
                  type="button"
                  onClick={() => runCurrentPhase()}
                  className="mb-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                >
                  Run keyword analysis
                </button>
              )}
              <KeywordDashboard
                output={keywords}
                streaming={isStreaming && !showProgress}
                claimedKeywords={sessionClaimedKeywords}
              />
              {keywords && !isStreaming && (
                <button
                  onClick={() => goTo("audit")}
                  className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors"
                >
                  Audit my resume →
                </button>
              )}
            </div>
          )}

          {step === "audit" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Resume Audit</h1>
              <p className="text-slate-400 text-sm mb-4">
                Every gap, weak bullet, and cliché — flagged before the rewrite.
              </p>
              {!audit && !phaseRunning && sessionLoaded && (
                <button
                  type="button"
                  onClick={() => runCurrentPhase()}
                  className="mb-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                >
                  Run resume audit
                </button>
              )}
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              <AuditPanel
                output={audit}
                streaming={isStreaming && !showProgress}
                sessionId={sessionId}
                initialClaimedKeywords={sessionClaimedKeywords}
                initialExtraNotes={sessionExtraNotes}
                initialBulletFixes={sessionBulletFixes}
                onReaudit={() => runCurrentPhase({ force: true })}
                onAuditEdited={(nextStale) => setStale((prev) => ({ ...prev, ...nextStale }))}
              />
              {audit && !isStreaming && (
                <button
                  onClick={() => goTo("rewrite")}
                  className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors"
                >
                  Rewrite my resume →
                </button>
              )}
            </div>
          )}

          {step === "rewrite" && (
            <div>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div>
                  <h1 className="text-xl font-bold mb-1">Tailored Rewrite</h1>
                  <p className="text-slate-400 text-sm">
                    Your resume, rewritten with exact JD phrasing and quality rules applied.
                  </p>
                </div>
                {tailored && (
                  <button
                    type="button"
                    onClick={() => recalculateAts()}
                    disabled={atsRecalcRunning || phaseRunning}
                    className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm font-semibold text-slate-200 hover:bg-slate-700 disabled:opacity-40"
                  >
                    {atsRecalcRunning ? "Recalculating…" : "Recalculate ATS Score"}
                  </button>
                )}
              </div>
              <LLMTierSelector
                value={llmTier}
                status={llmStatus}
                disabled={phaseRunning}
                onChange={setLlmTier}
                onRequestPurchase={handleRequestPurchase}
              />
              {!tailored && !phaseRunning && sessionLoaded && (
                <button
                  type="button"
                  onClick={() => runCurrentPhase()}
                  className="mb-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                >
                  Run tailored rewrite
                </button>
              )}
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
              <div className="flex flex-col lg:flex-row gap-6">
                <div className="flex-1 min-w-0">
                  <ResumeDiff
                    tailored={tailored}
                    streaming={isStreaming && !showProgress}
                    costInfo={costInfo}
                    sessionId={sessionId}
                    onEdited={(updated) => {
                      setTailored(updated);
                      setStale((prev) => ({ ...prev, "4": new Date().toISOString() }));
                    }}
                    onScopedRun={(scope) => runPhase("rewrite", { scope })}
                    phaseRunning={phaseRunning}
                    suggestionDraft={appliedSuggestion}
                    onClearSuggestion={() => setAppliedSuggestion(null)}
                  />
                </div>
                {(qa || atsRecalcRunning) && (
                  <div className="lg:w-80 shrink-0">
                    <ATSGuidancePanel
                      output={qa}
                      streaming={atsRecalcRunning}
                      scoreHistory={atsScoreHistory}
                      variant="sidebar"
                      onApplySuggestion={setAppliedSuggestion}
                    />
                  </div>
                )}
              </div>
              {tailored && !isStreaming && (
                <button
                  onClick={() => goTo("export")}
                  className="mt-6 px-6 py-2.5 bg-amber-400 text-slate-900 font-semibold rounded-lg hover:bg-amber-300 transition-colors"
                >
                  Run QA & export →
                </button>
              )}
            </div>
          )}

          {step === "export" && (
            <div>
              <h1 className="text-xl font-bold mb-1">QA & Export</h1>
              <p className="text-slate-400 text-sm mb-4">Final quality check before you download.</p>
              {!qa && !phaseRunning && sessionLoaded && (
                <button
                  type="button"
                  onClick={() => runCurrentPhase()}
                  className="mb-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                >
                  Run QA checklist
                </button>
              )}
              {showProgress && (
                <div className="mb-6">
                  <ProgressLog messages={progressLog} done={false} />
                </div>
              )}
              <div className="mb-8">
                <ATSGuidancePanel
                  output={qa}
                  streaming={isStreaming && !showProgress}
                  scoreHistory={atsScoreHistory}
                  variant="primary"
                  onApplySuggestion={(text) => {
                    setAppliedSuggestion(text);
                    goTo("rewrite");
                  }}
                />
              </div>
              <QAChecklist output={qa} streaming={isStreaming && !showProgress} />
              {qa && (
                <div className="mt-6">
                  <h2 className="text-slate-300 font-semibold mb-3 text-sm">Download your tailored resume</h2>
                  <ExportButtons sessionId={sessionId} disabled={false} />
                </div>
              )}
              {tailored && (
                <div className="mt-6 pt-6 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setCoverLetterOpen(true)}
                    className="px-4 py-2 rounded-lg bg-slate-800 border border-slate-600 text-sm font-semibold text-slate-200 hover:bg-slate-700"
                  >
                    Generate cover letter
                  </button>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      <CoverLetterPanel
        sessionId={sessionId}
        accessToken={authSession?.backendAccessToken}
        initial={coverLetter}
        open={coverLetterOpen}
        onClose={() => setCoverLetterOpen(false)}
      />

      <LLMUpgradePurchaseModal
        open={purchaseTier !== null}
        tier={purchaseTier}
        status={llmStatus}
        onClose={() => {
          setPurchaseTier(null);
          setCheckoutBusyCode(null);
        }}
        onCheckout={handleCheckout}
        busyCode={checkoutBusyCode}
      />
    </div>
  );
}

export default function SessionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
          Loading session…
        </div>
      }
    >
      <SessionContent />
    </Suspense>
  );
}
