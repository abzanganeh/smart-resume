"use client";

import { Suspense, useEffect, useState, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { useSSE, type SSEEvent } from "@/lib/sse";
import {
  triggerPhase,
  phaseEventsUrl,
  checkSession,
  getSessionResumeRecord,
  getVersions,
  restoreResumeVersion,
  ApiError,
  type PhaseRunScope,
  type KeywordExtractionOutput,
  type AuditOutput,
  type TailoredResumeOutput,
  type QAOutput,
  type CoverLetterOutput,
  type SessionResumeRecord,
} from "@/lib/api";
import { patchResume } from "@/lib/dashboard";
import { trackRecentSession } from "@/lib/recentSessions";
import { saveAuthReturnUrl } from "@/lib/auth/returnUrl";
import { refreshBackendSession } from "@/lib/auth/refreshBackendSession";
import { useSession } from "next-auth/react";
import { KeywordDashboard } from "@/components/session/KeywordDashboard";
import { AuditPanel } from "@/components/session/AuditPanel";
import { MetricsGate } from "@/components/session/MetricsGate";
import { ResumeDiff } from "@/components/session/ResumeDiff";
import { QAChecklist } from "@/components/session/QAChecklist";
import { ATSGuidancePanel, issueKey } from "@/components/session/ATSGuidancePanel";
import { summarizeEntryIssueBadges, scrollToResumeAnchor } from "@/lib/issueAnchors";
import { tryApplyMechanicalQuickWin } from "@/lib/mechanicalFix";
import type { IssueAnchor } from "@/lib/api";
import { ExportButtons } from "@/components/session/ExportButtons";
import { OpenInFlintButton } from "@/components/session/OpenInFlintButton";
import { CoverLetterPanel } from "@/components/session/CoverLetterPanel";
import { VersionHistory } from "@/components/session/VersionHistory";
import { ResizableSplit } from "@/components/session/ResizableSplit";
import { ProgressLog } from "@/components/session/ProgressLog";
import { StaleBanner } from "@/components/session/StaleBanner";
import { SessionAiControls } from "@/components/session/SessionAiControls";
import { cn } from "@/lib/utils";
import { AlertCircle, ChevronRight, MessageSquare, Sparkles, Zap } from "lucide-react";
import { ResumeChat } from "@/components/session/ResumeChat";
import { ExhaustionPaywall } from "@/components/billing/ExhaustionPaywall";
import { saveTailoredResume, commitTailoredResume, type ResumePatch } from "@/lib/api";
import { applyResumePatch, normalizeResumePatch } from "@/lib/applyResumePatch";
import { mergeSuggestionBatch, type ResumeSuggestion } from "@/lib/suggestions";
import {
  formatDuplicateApplicationPrompt,
  formatTrackerLimitError,
  trackApplicationWithDuplicatePrompt,
} from "@/lib/trackApplicationFlow";
import { TrackerApiError } from "@/lib/tracker";
import { dispatchCreditsExhausted } from "@/lib/offerPopup";

type Step = "analysis" | "rewrite" | "export";

const PHASE_FOR_STEP: Record<Exclude<Step, "analysis">, number> = {
  rewrite: 3,
  export: 4,
};
const STEPS: Step[] = ["analysis", "rewrite", "export"];
const STEP_LABELS: Record<Step, string> = {
  analysis: "Analysis",
  rewrite: "Tailored Rewrite",
  export: "QA & Export",
};

type AnalysisPipeline = { mode: "full" | "audit-only"; phase: 1 | 2 };

function normalizeStep(raw: string | null): Step {
  if (raw === "keywords" || raw === "audit") return "analysis";
  if (raw === "rewrite" || raw === "export") return raw;
  return "analysis";
}

function SessionContent() {
  const { id: sessionId } = useParams<{ id: string }>();
  const router = useRouter();
  const searchParams = useSearchParams();
  const [step, setStep] = useState<Step>(() => normalizeStep(searchParams.get("step")));

  const [keywords, setKeywords] = useState<KeywordExtractionOutput | null>(null);
  const [audit, setAudit] = useState<AuditOutput | null>(null);
  const [tailored, setTailored] = useState<TailoredResumeOutput | null>(null);
  const [qa, setQa] = useState<QAOutput | null>(null);
  // Fix 2: hydrate claimed keywords / extra notes / bullet fixes from session on load.
  const [sessionClaimedKeywords, setSessionClaimedKeywords] = useState<string[]>([]);
  const [sessionExtraNotes, setSessionExtraNotes] = useState("");
  const [sessionBulletFixes, setSessionBulletFixes] = useState<import("@/lib/api").BulletFixPayload[]>([]);
  const [sessionApprovedMetrics, setSessionApprovedMetrics] = useState<import("@/lib/api").ApprovedMetric[]>([]);
  const [exportCompany, setExportCompany] = useState<string | null>(null);
  const [hasJd, setHasJd] = useState(false);
  const [costInfo, setCostInfo] = useState<{ cost_formatted: string; provider: string; model: string } | null>(null);
  const [editorSyncKey, setEditorSyncKey] = useState(0);
  const [savedVersionNumber, setSavedVersionNumber] = useState(0);
  const [runError, setRunError] = useState<string | null>(null);
  const [runErrorCode, setRunErrorCode] = useState<string | null>(null);
  const [runErrorType, setRunErrorType] = useState<string | null>(null);
  const [sidebarTab, setSidebarTab] = useState<"ats" | "chat">("ats");
  const [chatPrefill, setChatPrefill] = useState<string | null>(null);
  const [issueQueue, setIssueQueue] = useState<import("@/lib/api").BlockingIssue[]>([]);
  const [issueQueueIdx, setIssueQueueIdx] = useState(0);
  const [expiryWarning, setExpiryWarning] = useState(false);
  const [phaseRunning, setPhaseRunning] = useState(false);
  const [progressLog, setProgressLog] = useState<string[]>([]);
  const [sessionLoaded, setSessionLoaded] = useState(false);
  const [phase1Complete, setPhase1Complete] = useState(false);
  const [stale, setStale] = useState<Record<string, string | null>>({ "3": null, "4": null });
  const [atsScoreHistory, setAtsScoreHistory] = useState<number[]>([]);
  const [pendingSuggestions, setPendingSuggestions] = useState<ResumeSuggestion[]>([]);
  const [suggestionError, setSuggestionError] = useState<string | null>(null);
  const [phase4RecalcActive, setPhase4RecalcActive] = useState(false);
  const [atsRecalcRunning, setAtsRecalcRunning] = useState(false);
  const [showRecalcConfirm, setShowRecalcConfirm] = useState(false);
  const [coverLetterOpen, setCoverLetterOpen] = useState(false);
  const [coverLetter, setCoverLetter] = useState<CoverLetterOutput | null>(null);

  const [aiSettingsOpen, setAiSettingsOpen] = useState(false);
  const [aiSettingsHighlight, setAiSettingsHighlight] = useState(false);
  const [namePromptRecord, setNamePromptRecord] = useState<SessionResumeRecord | null>(null);
  const [namePromptValue, setNamePromptValue] = useState("");
  const [namePromptSaving, setNamePromptSaving] = useState(false);
  const [trackLoading, setTrackLoading] = useState(false);
  const [trackError, setTrackError] = useState<string | null>(null);
  const pendingAtsFixRef = useRef<import("@/lib/api").BlockingIssue[]>([]);
  const [addressedAtsKeys, setAddressedAtsKeys] = useState<Set<string>>(() => new Set());
  const [skippedAtsKeys, setSkippedAtsKeys] = useState<Set<string>>(() => new Set());
  const entryIssueBadges = useMemo(() => {
    const visible = (qa?.blocking_issues ?? []).filter(
      (issue) => !skippedAtsKeys.has(issueKey(issue)),
    );
    return summarizeEntryIssueBadges(visible);
  }, [qa?.blocking_issues, skippedAtsKeys]);
  const scrollToIssueAnchor = useCallback((anchor: IssueAnchor) => {
    scrollToResumeAnchor(anchor);
  }, []);
  const applyMechanicalFix = useCallback(
    (issue: import("@/lib/api").BlockingIssue) => {
      if (!tailored) return;
      const updated = tryApplyMechanicalQuickWin(tailored, issue);
      if (!updated) return;
      setTailored(updated);
      setStale((prev) => ({ ...prev, "4": new Date().toISOString() }));
      setAddressedAtsKeys((prev) => new Set(prev).add(issueKey(issue)));
      void saveTailoredResume(sessionId, updated).catch((err) => {
        setRunError(err instanceof Error ? err.message : "Could not save mechanical fix.");
      });
    },
    [tailored, sessionId],
  );
  const runInFlightRef = useRef(false);
  const activeStepRef = useRef<Step>(step);
  const phase4RecalcRef = useRef(false);
  const tailoredBackupRef = useRef<TailoredResumeOutput | null>(null);
  const aiControlsRef = useRef<HTMLDivElement>(null);
  // Guard: track the last Phase 3 done event that already bumped editorSyncKey.
  // Prevents the main lastEvent effect from double-firing when unstable deps
  // (e.g. NextAuth's updateAuthSession) cause it to re-run with the same event.
  const lastPhase3DoneRef = useRef<SSEEvent | null>(null);
  const processedEventCountRef = useRef(0);
  const analysisPipelineRef = useRef<AnalysisPipeline | null>(null);

  const openAiSettings = useCallback(() => {
    setAiSettingsHighlight(true);
    window.setTimeout(() => setAiSettingsHighlight(false), 2500);
    setAiSettingsOpen(false);
    requestAnimationFrame(() => {
      setAiSettingsOpen(true);
      requestAnimationFrame(() => {
        aiControlsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });
  }, []);

  const llmErrorActive = runErrorType?.startsWith("llm_") ?? false;

  const { data: authSession, update: updateAuthSession } = useSession();
  const { connect, reset, lastEvent, events, isConnected, isDone, error: sseError } = useSSE();

  useEffect(() => {
    activeStepRef.current = step;
  }, [step]);

  // Keep React step in sync with browser back/forward (?step= in URL).
  useEffect(() => {
    const raw = searchParams.get("step");
    if (!raw) return;
    if (raw === "keywords" || raw === "audit") {
      router.replace(`/session/${sessionId}?step=analysis`, { scroll: false });
      if (step !== "analysis") setStep("analysis");
      return;
    }
    if (!STEPS.includes(raw as Step)) return;
    const urlStep = raw as Step;
    if (urlStep !== step) setStep(urlStep);
  }, [searchParams, sessionId, router, step]);

  // Remember tailoring location so re-auth returns here (not dashboard).
  useEffect(() => {
    saveAuthReturnUrl(`/session/${sessionId}?step=${step}`);
  }, [sessionId, step]);

  useEffect(() => {
    phase4RecalcRef.current = phase4RecalcActive;
  }, [phase4RecalcActive]);

  // Keep a backup of the latest tailored state so we can restore it if Phase 3 fails.
  useEffect(() => {
    if (tailored !== null) {
      tailoredBackupRef.current = tailored;
    }
  }, [tailored]);

  useEffect(() => {
    if (runErrorType?.startsWith("llm_")) {
      openAiSettings();
    }
  }, [runErrorType, openAiSettings]);

  const recordAtsScore = useCallback((qaOut: QAOutput) => {
    if (typeof qaOut.ats_score === "number") {
      setAtsScoreHistory((prev) => [...prev.slice(-4), qaOut.ats_score!]);
    }
  }, []);

  const applyPhaseOutputByNumber = useCallback((phaseNum: number, output: unknown) => {
    if (phaseNum === 1) {
      const k = output as KeywordExtractionOutput;
      if (!k.must_have_keywords?.length && !k.nice_to_have_keywords?.length) return;
      setKeywords(k);
      setPhase1Complete(true);
      return;
    }
    if (phaseNum === 2) {
      const o = output as Record<string, unknown>;
      if (!o || typeof o.overall_score !== "number" || !o.keyword_coverage) return;
      setAudit(output as AuditOutput);
      return;
    }
    if (phaseNum === 3) {
      setTailored(output as TailoredResumeOutput);
    }
    if (phaseNum === 4) {
      const qaOut = output as QAOutput;
      setQa(qaOut);
      recordAtsScore(qaOut);
      resetAtsIssueTracking();
    }
  }, [recordAtsScore]);

  const hydrateFromSession = useCallback((s: Awaited<ReturnType<typeof checkSession>>) => {
    setStale(s.stale ?? { "3": null, "4": null });
    setPhase1Complete(!!s.phase1_complete);
    setHasJd(!!s.has_jd);
    setExportCompany(s.export_company ?? null);

    const applyCached = (phaseNum: string) => {
      const cached = s.phases?.[phaseNum];
      if (cached?.status === "done" && cached.output) {
        applyPhaseOutputByNumber(Number(phaseNum), cached.output);
      }
    };
    applyCached("1");
    applyCached("2");
    applyCached("3");
    // Only restore QA if phase 4 is not stale relative to phase 3 edits.
    // If stale["4"] is set it means the tailored resume was edited after the
    // last QA run — showing the old result would give a false pass/fail.
    const phase4Stale = !!(s.stale?.["4"]);
    if (!phase4Stale) {
      applyCached("4");
    }

    const phase4 = s.phases?.["4"];
    if (!phase4Stale && phase4?.status === "done" && phase4.output) {
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
    if (s.approved_metrics?.length) setSessionApprovedMetrics(s.approved_metrics);
  }, [applyPhaseOutputByNumber]);

  const persistTailoredBeforeExport = useCallback(async () => {
    if (!tailored) return;
    await commitTailoredResume(sessionId, tailored);
  }, [sessionId, tailored]);

  const goTo = (s: Step) => {
    setStep(s);
    router.push(`/session/${sessionId}?step=${s}`, { scroll: false });
  };

  const goToExport = useCallback(async () => {
    if (tailored) {
      try {
        await persistTailoredBeforeExport();
      } catch {
        setRunError("Could not save resume changes before QA. Please try again.");
        return;
      }
    }
    goTo("export");
  }, [tailored, persistTailoredBeforeExport]);

  const runPhaseByNumber = useCallback(
    async (phase: number, options?: { force?: boolean; scope?: PhaseRunScope }) => {
      if (runInFlightRef.current) return;
      runInFlightRef.current = true;

      setRunError(null);
      setRunErrorCode(null);
      setRunErrorType(null);
      setPhaseRunning(true);
      if (options?.force) {
        if (phase === 1) setKeywords(null);
        if (phase === 2) setAudit(null);
        if (phase === 3) {
          tailoredBackupRef.current = tailoredBackupRef.current;
          setTailored(null);
        }
        if (phase === 4) setQa(null);
      }
      setProgressLog([]);
      processedEventCountRef.current = 0;
      reset();

      try {
        await triggerPhase(sessionId, phase, {
          force: options?.force,
          scope: options?.scope,
        });
        connect(phaseEventsUrl(sessionId, phase));
      } catch (e: unknown) {
        setPhaseRunning(false);
        runInFlightRef.current = false;
        analysisPipelineRef.current = null;
        setPhase4RecalcActive(false);
        setAtsRecalcRunning(false);
        const errorCode = e instanceof ApiError ? e.code : undefined;
        setRunErrorCode(errorCode ?? null);
        setRunError(e instanceof Error ? e.message : "Failed to start phase.");
        if (
          errorCode === "insufficient_credits" ||
          (e instanceof ApiError && e.status === 402)
        ) {
          dispatchCreditsExhausted();
          void refreshBackendSession(updateAuthSession);
        }
        if (phase === 3 && tailoredBackupRef.current) {
          setTailored(tailoredBackupRef.current);
        }
      }
    },
    [sessionId, connect, reset, updateAuthSession],
  );

  const runPhase = useCallback(
    async (targetStep: Exclude<Step, "analysis">, options?: { force?: boolean; scope?: PhaseRunScope }) => {
      const phase = PHASE_FOR_STEP[targetStep];
      await runPhaseByNumber(phase, options);
    },
    [runPhaseByNumber],
  );

  const runAnalysis = useCallback(
    async (options?: { force?: boolean; auditOnly?: boolean }) => {
      if (runInFlightRef.current) return;

      if (options?.auditOnly) {
        if (!keywords && !phase1Complete) {
          setRunError("Run full analysis first to extract JD keywords.");
          return;
        }
        analysisPipelineRef.current = { mode: "audit-only", phase: 2 };
        await runPhaseByNumber(2, { force: options.force });
        return;
      }

      analysisPipelineRef.current = { mode: "full", phase: 1 };
      if (options?.force) {
        setKeywords(null);
        setAudit(null);
      }
      await runPhaseByNumber(1, { force: options?.force });
    },
    [keywords, phase1Complete, runPhaseByNumber],
  );

  function buildIssuePrefill(issue: import("@/lib/api").BlockingIssue): string {
    return `Fix this issue in my resume:\n[${issue.category}] ${issue.description}\nSuggestion: ${issue.suggestion}`;
  }

  function startIssueQueue(issues: import("@/lib/api").BlockingIssue[]) {
    if (!issues.length) return;
    pendingAtsFixRef.current = [issues[0]!];
    setIssueQueue(issues);
    setIssueQueueIdx(0);
    setChatPrefill(buildIssuePrefill(issues[0]!));
    setSidebarTab("chat");
    goTo("rewrite");
  }

  function advanceIssueQueue(idx: number) {
    const next = idx + 1;
    setIssueQueueIdx(next);
    if (next < issueQueue.length) {
      pendingAtsFixRef.current = [issueQueue[next]!];
      setChatPrefill(buildIssuePrefill(issueQueue[next]!));
    } else {
      setIssueQueue([]);
      pendingAtsFixRef.current = [];
    }
  }

  function markAtsIssuesAddressed(issues: import("@/lib/api").BlockingIssue[]) {
    if (issues.length === 0) return;
    setAddressedAtsKeys((prev) => {
      const next = new Set(prev);
      issues.forEach((issue) => next.add(issueKey(issue)));
      return next;
    });
  }

  function skipAtsIssue(issue: import("@/lib/api").BlockingIssue) {
    setSkippedAtsKeys((prev) => {
      const next = new Set(prev);
      next.add(issueKey(issue));
      return next;
    });
  }

  function openChatForAtsIssues(message: string, issues: import("@/lib/api").BlockingIssue[]) {
    pendingAtsFixRef.current = issues;
    setChatPrefill(message);
    setSidebarTab("chat");
  }

  function resetAtsIssueTracking() {
    pendingAtsFixRef.current = [];
    setAddressedAtsKeys(new Set());
    setSkippedAtsKeys(new Set());
  }

  function addSuggestions(patches: ResumePatch[]) {
    if (patches.length === 0 || !tailored) return;
    setSuggestionError(null);
    const normalized = patches.map((p) => normalizeResumePatch(tailored, p));
    setPendingSuggestions((prev) => mergeSuggestionBatch(prev, normalized));
  }

  function acceptSuggestion(id: string) {
    const sug = pendingSuggestions.find((s) => s.id === id);
    if (!sug || !tailored) return;
    setSuggestionError(null);
    const patch = normalizeResumePatch(tailored, sug.patch);
    const { updated, applied, failureReason } = applyResumePatch(tailored, patch);
    if (applied) {
      setTailored(updated);
      setEditorSyncKey((k) => k + 1);
      // Edits invalidate the score (it'll change on next recalc), but we keep
      // the existing qa.blocking_issues/quick_wins visible so the user can keep
      // fixing the remaining items without losing the list. Just remove the
      // specific issue we were fixing (if any) and mark stale.
      setStale((prev) => ({ ...prev, "4": new Date().toISOString() }));
      const activeIssue =
        issueQueue.length > 0 && issueQueueIdx < issueQueue.length
          ? issueQueue[issueQueueIdx]
          : null;
      const toMark: import("@/lib/api").BlockingIssue[] = [...pendingAtsFixRef.current];
      if (activeIssue) {
        toMark.push(activeIssue);
      }
      if (toMark.length > 0) {
        markAtsIssuesAddressed(toMark);
        pendingAtsFixRef.current = [];
      }
      saveTailoredResume(sessionId, updated).catch((err) => {
        setRunError(
          err instanceof Error ? err.message : "Could not save this edit. Please try again.",
        );
      });
      if (issueQueue.length > 0 && issueQueueIdx < issueQueue.length) {
        advanceIssueQueue(issueQueueIdx);
      }
      setPendingSuggestions((prev) => prev.filter((s) => s.id !== id));
      return;
    }
    setSuggestionError(
      failureReason ?? "Could not apply this suggestion. Try the edit button or rephrase in chat.",
    );
    setPendingSuggestions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: "rejected" } : s)),
    );
    setTimeout(
      () => setPendingSuggestions((prev) => prev.filter((s) => s.id !== id)),
      1200,
    );
  }

  function rejectSuggestion(id: string) {
    setPendingSuggestions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: "rejected" } : s)),
    );
    setTimeout(
      () => setPendingSuggestions((prev) => prev.filter((s) => s.id !== id)),
      1200,
    );
  }

  function acceptAllSuggestions() {
    const pending = pendingSuggestions.filter((s) => s.status === "pending");
    if (!pending.length || !tailored) return;
    // Apply all patches sequentially against an accumulator to avoid stale-closure issues
    let current = tailored;
    const acceptedIds: string[] = [];
    for (const sug of pending) {
      const patch = normalizeResumePatch(current, sug.patch);
      const { updated, applied } = applyResumePatch(current, patch);
      if (applied) {
        current = updated;
        acceptedIds.push(sug.id);
      }
    }
    if (!acceptedIds.length) return;
    setTailored(current);
    setEditorSyncKey((k) => k + 1);
    setStale((prev) => ({ ...prev, "4": new Date().toISOString() }));
    setPendingSuggestions((prev) => prev.filter((s) => !acceptedIds.includes(s.id)));
    saveTailoredResume(sessionId, current).catch((err) => {
      setRunError(err instanceof Error ? err.message : "Could not save edits. Please try again.");
    });
  }

  function dismissSuggestion(id: string) {
    setPendingSuggestions((prev) => prev.filter((s) => s.id !== id));
  }

  const restoreVersionSnapshot = useCallback(async (snapshotId: string) => {
    try {
      const result = await restoreResumeVersion(sessionId, snapshotId);
      setTailored(result.tailored_output);
      setSavedVersionNumber(result.version);
      setEditorSyncKey((k) => k + 1);
      setStale(result.stale ?? { "3": null, "4": new Date().toISOString() });
      setPendingSuggestions([]);
      setSuggestionError(null);
    } catch (err) {
      setRunError(
        err instanceof Error ? err.message : "Could not restore that version.",
      );
    }
  }, [sessionId]);

  const recalculateAts = useCallback(async () => {
    if (runInFlightRef.current) return;
    setPhase4RecalcActive(true);
    setAtsRecalcRunning(true);
    await runPhase("export", { force: true });
  }, [runPhase]);

  const runCurrentPhase = useCallback(
    async (options?: { force?: boolean; scope?: PhaseRunScope; auditOnly?: boolean }) => {
      if (step === "analysis") {
        return runAnalysis(options);
      }
      if (step === "export" && tailored) {
        try {
          await persistTailoredBeforeExport();
        } catch {
          setRunError("Could not save resume changes before QA. Please try again.");
          return;
        }
      }
      return runPhase(step, options);
    },
    [step, tailored, persistTailoredBeforeExport, runPhase, runAnalysis],
  );

  useEffect(() => {
    if (
      lastEvent?.event === "done" &&
      lastEvent.phase === 3 &&
      lastPhase3DoneRef.current !== lastEvent
    ) {
      lastPhase3DoneRef.current = lastEvent;
      setEditorSyncKey((k) => k + 1);
      getVersions(sessionId)
        .then((r) => {
          const latest = r.versions.reduce((max, v) => Math.max(max, v.version), 0);
          setSavedVersionNumber(latest);
        })
        .catch(() => {});
    }
  }, [lastEvent, sessionId]);

  useEffect(() => {
    if (!lastEvent || events.length === 0) return;
    if (events.length <= processedEventCountRef.current) return;
    processedEventCountRef.current = events.length;

    const pipeline = analysisPipelineRef.current;
    const activeStep = activeStepRef.current;
    const isPhase4Recalc = phase4RecalcRef.current && lastEvent.phase === 4;

    let expectedPhase: number | undefined;
    if (activeStep === "analysis" && pipeline) {
      expectedPhase = pipeline.phase;
    } else if (activeStep !== "analysis") {
      expectedPhase = PHASE_FOR_STEP[activeStep];
    }

    if (
      lastEvent.phase !== undefined &&
      expectedPhase !== undefined &&
      lastEvent.phase !== expectedPhase &&
      !isPhase4Recalc
    ) {
      return;
    }

    if (lastEvent.event === "progress" && lastEvent.message) {
      setProgressLog((prev) => [...prev, lastEvent.message!]);
    }
    if (lastEvent.event === "partial" && lastEvent.data && lastEvent.phase !== undefined) {
      applyPhaseOutputByNumber(lastEvent.phase, lastEvent.data);
    }
    if (lastEvent.event === "cost_estimate" && lastEvent.cost_formatted) {
      setCostInfo({
        cost_formatted: lastEvent.cost_formatted,
        provider: lastEvent.provider!,
        model: lastEvent.model!,
      });
    }
    if (lastEvent.event === "done" && lastEvent.phase !== undefined) {
      applyPhaseOutputByNumber(lastEvent.phase, lastEvent.output);

      const chainAudit =
        pipeline?.mode === "full" && lastEvent.phase === 1 && activeStep === "analysis";

      if (chainAudit) {
        analysisPipelineRef.current = { mode: "full", phase: 2 };
        processedEventCountRef.current = 0;
        reset();
        void (async () => {
          try {
            await triggerPhase(sessionId, 2, {});
            connect(phaseEventsUrl(sessionId, 2));
          } catch (e: unknown) {
            setPhaseRunning(false);
            runInFlightRef.current = false;
            analysisPipelineRef.current = null;
            const errorCode = e instanceof ApiError ? e.code : undefined;
            setRunErrorCode(errorCode ?? null);
            setRunError(e instanceof Error ? e.message : "Failed to start audit phase.");
            if (
              errorCode === "insufficient_credits" ||
              (e instanceof ApiError && e.status === 402)
            ) {
              void refreshBackendSession(updateAuthSession);
            }
          }
        })();
        return;
      }

      if (pipeline && lastEvent.phase === 2) {
        analysisPipelineRef.current = null;
      }

      setPhaseRunning(false);
      runInFlightRef.current = false;
      if (lastEvent.phase === 3) {
        setStale((prev) => ({ ...prev, "3": null, "4": null }));
        if (authSession?.backendAccessToken) {
          void (async () => {
            try {
              const record = await getSessionResumeRecord(sessionId);
              if (
                record.tailoring_stage === "polished" &&
                !record.display_name?.trim()
              ) {
                setNamePromptRecord(record);
                setNamePromptValue(record.jd_title);
              }
            } catch {
              // Anonymous or record not synced yet.
            }
          })();
        }
      }
      if (lastEvent.phase === 4) {
        setStale((prev) => ({ ...prev, "4": null }));
        setPhase4RecalcActive(false);
        setAtsRecalcRunning(false);
        void refreshBackendSession(updateAuthSession);
      }
    }
    if (lastEvent.event === "error") {
      setPhaseRunning(false);
      runInFlightRef.current = false;
      analysisPipelineRef.current = null;
      setPhase4RecalcActive(false);
      setAtsRecalcRunning(false);
      setRunErrorType(lastEvent.error_type ?? null);
      setRunError(lastEvent.message ?? "Phase failed.");
    }
  }, [
    lastEvent,
    events.length,
    applyPhaseOutputByNumber,
    authSession?.backendAccessToken,
    sessionId,
    updateAuthSession,
    connect,
    reset,
  ]);

  // When the SSE stream drops mid-phase the server may still finish, but the
  // browser shows ERR_INCOMPLETE_CHUNKED_ENCODING. Clear the spinner and
  // restore the pre-regen resume so the user is not stuck forever.
  useEffect(() => {
    if (!sseError) return;
    setPhaseRunning(false);
    runInFlightRef.current = false;
    analysisPipelineRef.current = null;
    setPhase4RecalcActive(false);
    setAtsRecalcRunning(false);
    setRunError(sseError);
    setRunErrorType("connection_lost");
    if (activeStepRef.current === "rewrite" && tailoredBackupRef.current) {
      setTailored(tailoredBackupRef.current);
    }
  }, [sseError]);

  useEffect(() => {
    let cancelled = false;
    setSessionLoaded(false);
    setAtsScoreHistory([]);

    checkSession(sessionId)
      .then((s) => {
        if (cancelled) return;
        hydrateFromSession(s);
        trackRecentSession(sessionId, s.resume_raw?.slice(0, 40) || undefined);
        getVersions(sessionId)
          .then((r) => {
            if (cancelled) return;
            const latest = r.versions.reduce((max, v) => Math.max(max, v.version), 0);
            setSavedVersionNumber(latest);
          })
          .catch(() => {});
        setSessionLoaded(true);
      })
      .catch(() => {
        if (!cancelled) setSessionLoaded(true);
      });

    return () => {
      cancelled = true;
    };
  }, [sessionId, hydrateFromSession]);

  useEffect(() => {
    runInFlightRef.current = false;
    analysisPipelineRef.current = null;
    setPhaseRunning(false);
    setProgressLog([]);
    setRunError(null);
    setRunErrorCode(null);
    setRunErrorType(null);
    setShowRecalcConfirm(false);
    reset();
  }, [step, reset]);

  useEffect(() => {
    const timer = setTimeout(() => setExpiryWarning(true), 20 * 60 * 60 * 1000);
    return () => clearTimeout(timer);
  }, []);

  const stepHasOutput = {
    analysis: !!(keywords && audit),
    rewrite: !!tailored,
    export: !!qa,
  };

  const handleSaveResumeName = useCallback(async () => {
    if (!namePromptRecord || !authSession?.backendAccessToken) return;
    setNamePromptSaving(true);
    try {
      await patchResume(authSession.backendAccessToken, namePromptRecord.id, {
        display_name: namePromptValue.trim() || null,
      });
      setNamePromptRecord(null);
    } finally {
      setNamePromptSaving(false);
    }
  }, [authSession?.backendAccessToken, namePromptRecord, namePromptValue]);

  const handleTrackApplication = useCallback(async () => {
    if (!authSession?.backendAccessToken) return;
    setTrackLoading(true);
    setTrackError(null);
    try {
      const record = await getSessionResumeRecord(sessionId);
      const app = await trackApplicationWithDuplicatePrompt(
        authSession.backendAccessToken,
        {
          resume_record_id: record.id,
          jd_title: record.jd_title,
          jd_company: record.jd_company,
          status: "draft",
        },
        (err) =>
          window.confirm(
            `${formatDuplicateApplicationPrompt(err)}\n\nAdd this application anyway?`,
          ),
      );
      router.push(`/tracker/${app.id}`);
    } catch (e) {
      if (e instanceof TrackerApiError && e.code === "tracker_limit_reached") {
        setTrackError(formatTrackerLimitError(e));
      } else if (e instanceof TrackerApiError && e.code === "duplicate_application") {
        setTrackError(null);
      } else {
        setTrackError(e instanceof Error ? e.message : "Could not create application.");
      }
    } finally {
      setTrackLoading(false);
    }
  }, [authSession?.backendAccessToken, router, sessionId]);

  const tabsUnlocked = phase1Complete;
  const isStreaming = phaseRunning || (isConnected && !isDone);
  const showProgress = phaseRunning;

  const auditSectionVisible = !!audit || (phaseRunning && !!keywords);
  const keywordsStreaming = isStreaming && !showProgress && !audit;
  const auditStreaming = isStreaming && !showProgress && !!keywords && !audit;

  const staleMessageForStep = (s: Step): string | null => {
    if (s === "rewrite" && stale["3"]) {
      return "Your audit changed. Re-run Phase 3 to apply updates.";
    }
    if (s === "export" && stale["4"]) {
      return "Your rewrite changed. Re-run Phase 4 to refresh QA.";
    }
    return null;
  };

  const sessionAiControls = (
    <div
      ref={aiControlsRef}
      className={cn(
        "rounded-xl transition-shadow",
        aiSettingsHighlight && "ring-2 ring-amber-400 ring-offset-2 ring-offset-slate-900",
      )}
    >
      <SessionAiControls
        phaseRunning={phaseRunning}
        open={aiSettingsOpen}
        onOpenChange={setAiSettingsOpen}
        modelLabel="Included with your subscription tier"
      />
    </div>
  );

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
      {expiryWarning && (
        <div className="bg-amber-500/10 dark:bg-amber-400/10 border-b border-amber-400/30 px-6 py-2 text-center text-amber-700 dark:text-amber-400 text-sm">
          <AlertCircle className="w-4 h-4 inline mr-1.5 -mt-0.5" />
          Your session expires in 4 hours. Download your resume before it&apos;s gone.
        </div>
      )}

      {namePromptRecord && authSession?.backendAccessToken && (
        <div className="bg-emerald-400/10 border-b border-emerald-400/30 px-6 py-3">
          <p className="text-sm text-emerald-800 dark:text-emerald-200 mb-2">
            Name this resume for your dashboard (you can change it later):
          </p>
          <div className="flex flex-wrap items-center gap-2 max-w-xl">
            <input
              type="text"
              value={namePromptValue}
              onChange={(e) => setNamePromptValue(e.target.value)}
              className="flex-1 min-w-[12rem] bg-white dark:bg-slate-900 border border-slate-300 dark:border-slate-700 rounded-lg px-3 py-2 text-sm text-slate-900 dark:text-slate-100"
              placeholder="e.g. Acme — Staff Engineer"
            />
            <button
              type="button"
              disabled={namePromptSaving}
              onClick={() => void handleSaveResumeName()}
              className="text-sm font-medium bg-emerald-500 text-slate-900 px-3 py-2 rounded-lg disabled:opacity-50"
            >
              Save name
            </button>
            <button
              type="button"
              onClick={() => setNamePromptRecord(null)}
              className="text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 px-2 py-2"
            >
              Skip
            </button>
          </div>
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
                    ${active ? "bg-amber-400 text-slate-900" : hasOutput ? "bg-slate-200 dark:bg-slate-700 text-slate-800 dark:text-slate-200 hover:bg-slate-300 dark:hover:bg-slate-600" : clickable ? "bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 hover:bg-slate-200 dark:hover:bg-slate-700" : "bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 cursor-not-allowed"}`}
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

        <p className="text-xs text-slate-600 dark:text-slate-400 mb-4">
          Click any step above to jump back — your progress is saved.
        </p>

        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8">
          {!llmErrorActive && sessionAiControls}

          {runError && (
            <div className="flex flex-col sm:flex-row sm:items-start gap-2 text-sm bg-red-400/10 border border-red-400/20 rounded-lg p-3 mb-6">
              <AlertCircle className="w-4 h-4 mt-0.5 shrink-0 text-red-700 dark:text-red-400" />
              <div className="flex-1 min-w-0">
                {runErrorType?.startsWith("llm_") && (
                  <span className="inline-block text-amber-700 dark:text-amber-400 text-xs font-semibold uppercase tracking-wide mr-2 bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/20 rounded px-1.5 py-0.5 mb-1">
                    AI model error
                  </span>
                )}
                <span className="text-red-700 dark:text-red-300">{runError}</span>
                {runErrorType?.startsWith("llm_") && (
                  <p className="text-xs text-slate-600 dark:text-slate-400 mt-2">
                    {runErrorType === "llm_insufficient_credits" ? (
                      <>
                        Provider credits are exhausted. Switch to Platform AI (Gemini) below or add
                        credits at your provider, then retry — no need to start a new session.{" "}
                        <a
                          href="https://openrouter.ai/settings/credits"
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-amber-700 dark:text-amber-400 underline hover:no-underline"
                        >
                          OpenRouter credits
                        </a>
                      </>
                    ) : (
                      <>
                        Switch to Platform AI in the panel below, then retry — no need to start a
                        new session.
                      </>
                    )}
                  </p>
                )}
              </div>
              <div className="flex flex-wrap gap-3 sm:ml-auto shrink-0">
                {runErrorType?.startsWith("llm_") && (
                  <button
                    type="button"
                    onClick={openAiSettings}
                    className="text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 text-xs font-semibold underline hover:no-underline"
                  >
                    Change AI settings
                  </button>
                )}
                {runErrorCode === "master_resume_required" ? (
                  <Link
                    href="/profile"
                    className="whitespace-nowrap underline hover:no-underline text-red-700 dark:text-red-400"
                    onClick={() => setRunError(null)}
                  >
                    Upload master resume →
                  </Link>
                ) : runErrorCode === "insufficient_credits" ? (
                  !authSession?.backendAccessToken ? (
                    <Link
                      href="/billing"
                      className="whitespace-nowrap underline hover:no-underline text-red-700 dark:text-red-400"
                      onClick={() => setRunError(null)}
                    >
                      View billing →
                    </Link>
                  ) : null
                ) : runErrorCode === "subscription_required" ? (
                  <Link
                    href="/billing"
                    className="whitespace-nowrap underline hover:no-underline text-red-700 dark:text-red-400"
                    onClick={() => setRunError(null)}
                  >
                    View billing →
                  </Link>
                ) : (
                  <button
                    type="button"
                    onClick={() => {
                      setRunError(null);
                      setRunErrorCode(null);
                      setRunErrorType(null);
                      runCurrentPhase({ force: true });
                    }}
                    className="underline hover:no-underline text-red-700 dark:text-red-400"
                  >
                    Retry
                  </button>
                )}
              </div>
            </div>
          )}

          {runErrorCode === "insufficient_credits" && authSession?.backendAccessToken && (
            <ExhaustionPaywall
              token={authSession.backendAccessToken}
              className="mb-6"
              compact
              onCreditsRefreshed={() => {
                setRunError(null);
                setRunErrorCode(null);
                setRunErrorType(null);
              }}
            />
          )}

          {llmErrorActive && <div className="mb-6">{sessionAiControls}</div>}

          {staleMessageForStep(step) && (
            <StaleBanner
              message={staleMessageForStep(step)!}
              onRerun={() => runCurrentPhase({ force: true })}
              running={phaseRunning}
            />
          )}

          {step === "analysis" && (
            <div>
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div>
                  <h1 className="text-xl font-bold mb-1">Analysis</h1>
                  <p className="text-slate-600 dark:text-slate-400 text-sm">
                    JD keywords and resume audit — one run extracts keywords then scores your resume.
                  </p>
                </div>
                <div className="flex items-center gap-2 shrink-0">
                  {phase1Complete && (
                    <Link href="/session/new" className="text-xs text-amber-700 dark:text-amber-400 hover:text-amber-800 dark:hover:text-amber-300 underline">
                      New session
                    </Link>
                  )}
                  {keywords && !phaseRunning && (
                    <>
                      <button
                        type="button"
                        onClick={() => runCurrentPhase({ auditOnly: true, force: true })}
                        disabled={phaseRunning}
                        className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
                      >
                        Re-run audit only
                      </button>
                      {audit && (
                        <button
                          type="button"
                          onClick={() => runCurrentPhase({ force: true })}
                          disabled={phaseRunning}
                          className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
                        >
                          Re-run full analysis
                        </button>
                      )}
                    </>
                  )}
                </div>
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
                  Run analysis
                </button>
              )}
              {keywords && !audit && !phaseRunning && sessionLoaded && (
                <button
                  type="button"
                  onClick={() => runCurrentPhase({ auditOnly: true })}
                  className="mb-6 px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                >
                  Run audit (keywords ready)
                </button>
              )}
              <div className="space-y-8">
                <section>
                  <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide mb-3">
                    JD Keywords
                  </h2>
                  <KeywordDashboard
                    output={keywords}
                    streaming={keywordsStreaming}
                    claimedKeywords={sessionClaimedKeywords}
                  />
                </section>
                {auditSectionVisible && (
                  <section>
                    <h2 className="text-sm font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide mb-3">
                      Resume Audit
                    </h2>
                    <AuditPanel
                      output={audit}
                      streaming={auditStreaming}
                      sessionId={sessionId}
                      initialClaimedKeywords={sessionClaimedKeywords}
                      initialExtraNotes={sessionExtraNotes}
                      initialBulletFixes={sessionBulletFixes}
                      onAuditEdited={(nextStale) => setStale((prev) => ({ ...prev, ...nextStale }))}
                    />
                    {audit && !isStreaming && (audit.unverified_metrics?.length ?? 0) > 0 && (
                      <div className="mt-6">
                        <MetricsGate
                          sessionId={sessionId}
                          unverifiedMetrics={audit.unverified_metrics!}
                          initialApprovedMetrics={sessionApprovedMetrics}
                          onSaved={setSessionApprovedMetrics}
                        />
                      </div>
                    )}
                  </section>
                )}
              </div>
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
                  <p className="text-slate-600 dark:text-slate-400 text-sm">
                    Your resume, rewritten with exact JD phrasing and quality rules applied.
                  </p>
                </div>
                {tailored && (
                  <div className="flex items-center gap-2 shrink-0">
                    <button
                      type="button"
                      onClick={() => runCurrentPhase({ force: true })}
                      disabled={phaseRunning}
                      className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
                    >
                      {phaseRunning ? "Regenerating…" : "Regenerate Resume"}
                    </button>
                    {showRecalcConfirm ? (
                      <>
                        <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/30 text-xs text-amber-700 dark:text-amber-300">
                          <Zap className="w-3.5 h-3.5 shrink-0" />
                          Costs 1 credit
                        </div>
                        <button
                          type="button"
                          onClick={() => { setShowRecalcConfirm(false); recalculateAts(); }}
                          disabled={atsRecalcRunning || phaseRunning}
                          className="px-3 py-1.5 rounded-lg bg-amber-400 text-slate-900 text-xs font-semibold hover:bg-amber-300 disabled:opacity-40"
                        >
                          Confirm
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowRecalcConfirm(false)}
                          className="px-3 py-1.5 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-xs text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700"
                        >
                          Cancel
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        onClick={() => setShowRecalcConfirm(true)}
                        disabled={atsRecalcRunning || phaseRunning}
                        className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700 disabled:opacity-40"
                      >
                        {atsRecalcRunning ? "Recalculating…" : "Recalculate ATS Score"}
                      </button>
                    )}
                  </div>
                )}
              </div>
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
              {tailored && authSession?.backendAccessToken && (
                <div className="mb-4 flex flex-wrap items-center gap-3">
                  <button
                    type="button"
                    onClick={() => void handleTrackApplication()}
                    disabled={trackLoading || phaseRunning}
                    data-testid="track-application-from-session"
                    className="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-40"
                  >
                    {trackLoading ? "Creating…" : "Track this application"}
                  </button>
                  {trackError && <p className="text-xs text-red-700 dark:text-red-400">{trackError}</p>}
                </div>
              )}
              {tailored && (
                <div className="mb-4">
                  <VersionHistory
                    sessionId={sessionId}
                    currentVersion={savedVersionNumber}
                    onRestore={restoreVersionSnapshot}
                  />
                </div>
              )}
              <ResizableSplit
                storageKey="smart-resume:tailoring-sidebar-width"
                defaultRightWidth={400}
                minRightWidth={300}
                maxRightWidth={760}
                minLeftWidth={340}
                left={
                  <>
                    {suggestionError && (
                      <div className="mb-4 rounded-lg border border-red-500/40 bg-red-500/10 px-4 py-3 text-sm text-red-800 dark:text-red-200">
                        {suggestionError}
                      </div>
                    )}
                    <ResumeDiff
                      tailored={tailored}
                      editorRevision={editorSyncKey}
                      streaming={isStreaming && !showProgress}
                      costInfo={costInfo}
                      sessionId={sessionId}
                      onEdited={(updated, meta) => {
                        setTailored(updated);
                        setStale((prev) => ({ ...prev, "4": new Date().toISOString() }));
                        if (meta?.source === "undo" || meta?.source === "redo") {
                          saveTailoredResume(sessionId, updated).catch((err) => {
                            setRunError(
                              err instanceof Error
                                ? err.message
                                : "Could not save this edit. Please try again.",
                            );
                          });
                        }
                      }}
                      onVersionSnapshot={setSavedVersionNumber}
                      onScopedRun={(scope) => runPhase("rewrite", { scope })}
                      phaseRunning={phaseRunning}
                      suggestions={pendingSuggestions}
                      onAcceptSuggestion={acceptSuggestion}
                      onAcceptAllSuggestions={acceptAllSuggestions}
                      onRejectSuggestion={rejectSuggestion}
                      onDismissSuggestion={dismissSuggestion}
                      entryIssueBadges={entryIssueBadges}
                    />
                  </>
                }
                right={
                  <div className="flex flex-col h-[clamp(480px,75vh,820px)] border border-slate-300 dark:border-slate-700 rounded-xl overflow-hidden bg-white/60 dark:bg-slate-900/60">
                    {/* Tab bar */}
                    <div className="flex border-b border-slate-300 dark:border-slate-700 shrink-0">
                      <button
                        type="button"
                        onClick={() => setSidebarTab("ats")}
                        className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-semibold transition-colors ${
                          sidebarTab === "ats"
                            ? "text-amber-700 dark:text-amber-400 border-b-2 border-amber-400 bg-slate-100/40 dark:bg-slate-800/40"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                        }`}
                      >
                        <Sparkles className="w-3.5 h-3.5" />
                        ATS Guidance
                        {qa && (
                          <span className="ml-0.5 tabular-nums text-[10px]">{qa.ats_score}/100</span>
                        )}
                      </button>
                      <button
                        type="button"
                        onClick={() => setSidebarTab("chat")}
                        className={`flex-1 flex items-center justify-center gap-1.5 px-3 py-2.5 text-xs font-semibold transition-colors ${
                          sidebarTab === "chat"
                            ? "text-amber-700 dark:text-amber-400 border-b-2 border-amber-400 bg-slate-100/40 dark:bg-slate-800/40"
                            : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200"
                        }`}
                      >
                        <MessageSquare className="w-3.5 h-3.5" />
                        Chat
                      </button>
                    </div>

                    {/* Tab content — keep both mounted so ATS dismiss state survives tab switches */}
                    <div className={cn("p-4 overflow-y-auto flex-1 min-h-0", sidebarTab !== "ats" && "hidden")}>
                        {(qa || atsRecalcRunning) ? (
                          <ATSGuidancePanel
                            output={qa}
                            streaming={atsRecalcRunning}
                            scoreHistory={atsScoreHistory}
                            variant="sidebar"
                            staleSince={stale["4"]}
                            onRecalculate={recalculateAts}
                            recalculateDisabled={atsRecalcRunning || phaseRunning}
                            addressedKeys={addressedAtsKeys}
                            skippedKeys={skippedAtsKeys}
                            onSkipIssue={skipAtsIssue}
                            onStartQueue={startIssueQueue}
                            onSendToChat={openChatForAtsIssues}
                            onScrollToAnchor={scrollToIssueAnchor}
                            onApplyMechanicalFix={applyMechanicalFix}
                          />
                        ) : (
                          <p className="text-slate-600 dark:text-slate-400 text-xs py-4 text-center">
                            Run QA &amp; Export to see your ATS score and guidance.
                          </p>
                        )}
                    </div>
                    <div className={cn("flex-1 flex flex-col min-h-0", sidebarTab !== "chat" && "hidden")}>
                        <ResumeChat
                          sessionId={sessionId}
                          tailored={tailored}
                          prefillMessage={chatPrefill}
                          onClearPrefill={() => setChatPrefill(null)}
                          queueBanner={
                            issueQueue.length > 0 && issueQueueIdx < issueQueue.length
                              ? {
                                  issue: issueQueue[issueQueueIdx]!,
                                  current: issueQueueIdx + 1,
                                  total: issueQueue.length,
                                  onSkip: () => advanceIssueQueue(issueQueueIdx),
                                }
                              : null
                          }
                          onSuggestPatches={addSuggestions}
                        />
                    </div>
                  </div>
                }
              />
              {tailored && !isStreaming && (
                <button
                  onClick={() => void goToExport()}
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
              <p className="text-slate-600 dark:text-slate-400 text-sm mb-4">Final quality check before you download.</p>
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
                  staleSince={stale["4"]}
                  onRecalculate={recalculateAts}
                  recalculateDisabled={atsRecalcRunning || phaseRunning}
                  addressedKeys={addressedAtsKeys}
                  skippedKeys={skippedAtsKeys}
                  onSkipIssue={skipAtsIssue}
                  onStartQueue={startIssueQueue}
                  onSendToChat={(msg, issues) => {
                    openChatForAtsIssues(msg, issues);
                    goTo("rewrite");
                  }}
                  onScrollToAnchor={scrollToIssueAnchor}
                  onApplyMechanicalFix={applyMechanicalFix}
                />
              </div>
              <QAChecklist output={qa} streaming={isStreaming && !showProgress} />
              {qa && (
                <div className="mt-6 space-y-4">
                  <div>
                    <h2 className="text-slate-700 dark:text-slate-300 font-semibold mb-3 text-sm">Download your tailored resume</h2>
                    <ExportButtons
                      sessionId={sessionId}
                      disabled={false}
                      candidateName={tailored?.contact?.name}
                      companyName={exportCompany ?? undefined}
                      hasJd={hasJd}
                    />
                  </div>
                  <div>
                    <h2 className="text-slate-700 dark:text-slate-300 font-semibold mb-3 text-sm">Prepare for the interview</h2>
                    <OpenInFlintButton sessionId={sessionId} disabled={false} />
                  </div>
                </div>
              )}
              {tailored && (
                <div className="mt-6 pt-6 border-t border-slate-200 dark:border-slate-800">
                  <button
                    type="button"
                    onClick={() => setCoverLetterOpen(true)}
                    className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700"
                  >
                    Generate cover letter
                  </button>
                </div>
              )}
              {qa && (
                <div className="mt-8 pt-6 border-t border-slate-200 dark:border-slate-800 flex flex-wrap gap-3">
                  <Link
                    href="/dashboard"
                    className="px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-400 dark:border-slate-600 text-sm font-semibold text-slate-800 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700"
                  >
                    Return to dashboard
                  </Link>
                  <Link
                    href="/session/new"
                    className="px-4 py-2 rounded-lg bg-amber-400 text-slate-900 text-sm font-semibold hover:bg-amber-300"
                  >
                    Start new tailor
                  </Link>
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

    </div>
  );
}

export default function SessionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
          Loading session…
        </div>
      }
    >
      <SessionContent />
    </Suspense>
  );
}
