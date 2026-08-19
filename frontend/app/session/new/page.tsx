"use client";

import { Suspense, useEffect, useRef, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useSession } from "next-auth/react";
import { getExtensionJobDescription } from "@/lib/extensionJobDescription";
import {
  captureExtensionHandoffFromParams,
  getExtensionHandoff,
  buildSessionNewUrl,
  saveExtensionHandoff,
} from "@/lib/extensionHandoff";
import { clearCheckupHandoff, getCheckupHandoff } from "@/lib/checkupHandoff";
import { shouldReviewExtensionJd } from "@/lib/jdCompleteness";
import { getJob } from "@/lib/jobs";
import { ResumeUploader } from "@/components/wizard/ResumeUploader";
import { UserInfoForm } from "@/components/wizard/UserInfoForm";
import { JDInput } from "@/components/wizard/JDInput";
import {
  createSession,
  saveUserInfo,
  submitJD,
  checkSession,
  pasteResumeText,
  type JDPayload,
  type ParsedResume,
  type UserInfoPayload,
} from "@/lib/api";

// Resume → Job Description → Your Info (platform AI — no BYOK step)
const STEPS = ["resume", "jd", "info"] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  resume: "Upload Resume",
  jd:     "Job Description",
  info:   "Your Info",
};

function NewSessionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { data: session } = useSession();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [step, setStep] = useState<Step>((searchParams.get("step") as Step) ?? "resume");

  // Carry forward between steps
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null);
  const [jdText, setJdText] = useState("");
  const [jdSourceUrl, setJdSourceUrl] = useState<string | null>(null);
  const [jdReviewRecommended, setJdReviewRecommended] = useState(false);
  const [infoHydrating, setInfoHydrating] = useState(false);

  const [loading, setLoading] = useState(false);
  const jdLoadedRef = useRef(false);
  const checkupResumeAppliedRef = useRef(false);
  const [hasMasterResume, setHasMasterResume] = useState<boolean | undefined>(undefined);

  // Restore extension handoff if OAuth stripped jd_id from the URL.
  useEffect(() => {
    const urlHandoff = captureExtensionHandoffFromParams(searchParams);
    if (urlHandoff) return;

    const stored = getExtensionHandoff();
    if (stored && !searchParams.get("jd_id")) {
      router.replace(buildSessionNewUrl(stored));
    }
  }, [searchParams, router]);

  useEffect(() => {
    async function initSession() {
      // No ?step= param means the user explicitly navigated to /session/new
      // (e.g. clicked "New session" in the nav while mid-wizard).  Always
      // create a fresh session in that case — never reuse the in-progress one.
      const isFreshStart = !searchParams.get("step");

      if (!isFreshStart) {
        const existing = sessionStorage.getItem("smart_resume_session_id");
        if (existing) {
          try {
            const res = await fetch(
              `${process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000"}/api/sessions/${existing}`
            );
            if (res.ok) {
              setSessionId(existing);
              return;
            }
          } catch {
            // backend unreachable — fall through to create
          }
          sessionStorage.removeItem("smart_resume_session_id");
        }
      } else {
        // Discard any in-progress session so the new one starts clean.
        sessionStorage.removeItem("smart_resume_session_id");
      }

      try {
        const r = await createSession();
        setSessionId(r.session_id);
        sessionStorage.setItem("smart_resume_session_id", r.session_id);
      } catch {
        // backend not running — will show error when user tries to upload
      }
    }

    initSession();

    const jdFromQuery = searchParams.get("jd");
    if (jdFromQuery) {
      try {
        setJdText(decodeURIComponent(jdFromQuery));
        setStep("jd");
      } catch {
        setJdText(jdFromQuery);
        setStep("jd");
      }
      return;
    }

    if (searchParams.get("from") === "checkup") {
      const handoff = getCheckupHandoff();
      if (handoff) {
        let jd = handoff.jdText;
        const title = handoff.jobTitle.trim();
        if (title && !jd.toLowerCase().includes(title.toLowerCase())) {
          jd = `${title}\n\n${jd}`;
        }
        setJdText(jd);
        setStep("jd");
        if (handoff.resumeText.trim()) {
          sessionStorage.setItem("sr_checkup_resume_text", handoff.resumeText);
        }
        clearCheckupHandoff();
      }
    }
  }, [searchParams, router]);

  // Checkup funnel: auto-apply resume text saved before auth redirect.
  useEffect(() => {
    if (!sessionId || checkupResumeAppliedRef.current) return;
    const resumeText = sessionStorage.getItem("sr_checkup_resume_text");
    if (!resumeText?.trim()) return;
    checkupResumeAppliedRef.current = true;
    void (async () => {
      try {
        const result = await pasteResumeText(sessionId, resumeText);
        setParsedResume(result.parsed);
        sessionStorage.removeItem("sr_checkup_resume_text");
      } catch {
        // User can still upload manually on the resume step.
      }
    })();
  }, [sessionId]);

  // Separate effect: load JD from extension or jobs API once the backend token
  // is available. Runs when token arrives (may be after the init effect above).
  const backendToken = session?.backendAccessToken;
  useEffect(() => {
    if (!backendToken) return;

    const urlJdId = searchParams.get("jd_id");
    const storedHandoff = getExtensionHandoff();
    const jdId = urlJdId ?? storedHandoff?.jd_id ?? null;
    const jdSource = searchParams.get("source") ?? storedHandoff?.source ?? "extension";
    const jdReviewFlag =
      searchParams.get("jd_review") === "1" || storedHandoff?.jd_review === true;

    if (jdId && !urlJdId) {
      saveExtensionHandoff({
        jd_id: jdId,
        source: jdSource,
        step: storedHandoff?.step ?? "jd",
        jd_review: jdReviewFlag,
      });
      router.replace(
        buildSessionNewUrl({
          jd_id: jdId,
          source: jdSource,
          step: storedHandoff?.step ?? "jd",
          jd_review: jdReviewFlag,
        }),
      );
    }

    void (async () => {
      try {
        const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${BASE}/api/profile/resume`, {
          headers: { Authorization: `Bearer ${backendToken}` },
        });
        if (res.ok) {
          const profile = await res.json() as { chunk_count?: number };
          setHasMasterResume((profile.chunk_count ?? 0) > 0);
        } else {
          setHasMasterResume(false);
        }
      } catch {
        setHasMasterResume(false);
      }
    })();

    if (!jdId) return;

    // Only load the JD once. Subsequent searchParams changes (e.g. goTo("info")
    // changing the URL) must not reset the wizard back to the JD step.
    if (jdLoadedRef.current) return;

    void (async () => {
      try {
        if (jdSource === "extension") {
          const saved = await getExtensionJobDescription(backendToken, jdId);
          if (saved.text?.trim()) {
            jdLoadedRef.current = true;
            setJdSourceUrl(saved.url);
            setJdReviewRecommended(
              shouldReviewExtensionJd(jdSource, saved.url, jdReviewFlag),
            );

            // Resume only when the linked session finished the wizard (info saved
            // or keywords already run). A JD-only link would hijack refresh mid-flow.
            if (saved.session_id) {
              try {
                const snap = await checkSession(saved.session_id);
                if (snap.has_user_info || snap.phase1_complete) {
                  router.replace(`/session/${saved.session_id}?step=analysis`);
                  return;
                }
              } catch {
                // Session expired — continue wizard with this JD text.
              }
            }

            setJdText(saved.text);
            const urlStep = searchParams.get("step");
            const onLaterWizardStep = urlStep === "info" || urlStep === "resume";
            if (!onLaterWizardStep) {
              setStep("jd");
              const reviewParams = shouldReviewExtensionJd(jdSource, saved.url, jdReviewFlag)
                ? "&jd_review=1"
                : "";
              router.replace(
                `/session/new?step=jd&jd_id=${jdId}&source=extension${reviewParams}`,
              );
            }
          }
          return;
        }
        const job = await getJob(backendToken, jdId);
        if (job.description?.trim()) {
          jdLoadedRef.current = true;
          setJdText(job.description);
          setStep("jd");
          router.replace(`/session/new?step=jd&jd_id=${jdId}&source=jobs`);
        }
      } catch {
        // User can paste JD manually if fetch fails
      }
    })();
  }, [backendToken, searchParams, router]);

  const goTo = (s: Step) => {
    setStep(s);
    const params = new URLSearchParams();
    params.set("step", s);
    const handoff = getExtensionHandoff();
    const jdId = searchParams.get("jd_id") ?? handoff?.jd_id;
    const jdSource = searchParams.get("source") ?? handoff?.source;
    const jdReview = searchParams.get("jd_review") === "1" || handoff?.jd_review === true;
    if (jdId) params.set("jd_id", jdId);
    if (jdSource) params.set("source", jdSource);
    if (jdReview) params.set("jd_review", "1");
    router.replace(`/session/new?${params.toString()}`);
  };

  // Browser back/forward (and explicit "New session" clicks): keep wizard
  // step aligned with the URL.  A missing ?step= param means the user
  // navigated to /session/new fresh — reset to the first step so the wizard
  // doesn't stay frozen on whatever step it was on before.
  useEffect(() => {
    const raw = searchParams.get("step");
    if (!raw || !STEPS.includes(raw as Step)) {
      // If a jd_id is present, the token effect will set step once the JD
      // loads and push ?step=jd into the URL. Resetting here would race.
      if (searchParams.get("jd_id")) return;
      // No valid step param → fresh navigation; clear in-memory wizard state.
      if (step !== "resume") {
        setStep("resume");
        setParsedResume(null);
        setJdText("");
        setSessionId(null);
      }
      return;
    }
    const urlStep = raw as Step;
    if (urlStep !== step) setStep(urlStep);
  }, [searchParams, step]);

  // Hydrate resume parse state when landing on info (refresh or master import).
  useEffect(() => {
    if (step !== "info" || !sessionId || parsedResume) return;

    let cancelled = false;
    setInfoHydrating(true);
    void (async () => {
      try {
        const snapshot = await checkSession(sessionId);
        if (cancelled) return;
        if (snapshot.resume_parsed) {
          setParsedResume(snapshot.resume_parsed);
          return;
        }

        if (!backendToken) return;
        const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
        const res = await fetch(`${BASE}/api/profile/resume`, {
          headers: { Authorization: `Bearer ${backendToken}` },
        });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as { raw_text?: string };
        if (!data.raw_text?.trim()) return;
        const result = await pasteResumeText(sessionId, data.raw_text);
        if (!cancelled) setParsedResume(result.parsed);
      } catch {
        // User can fill the form manually or go back to upload resume.
      } finally {
        if (!cancelled) setInfoHydrating(false);
      }
    })();

    return () => {
      cancelled = true;
      setInfoHydrating(false);
    };
  }, [step, sessionId, parsedResume, backendToken]);

  // If user backs into the wizard after finishing, skip to the live session.
  useEffect(() => {
    if (step !== "info" || !sessionId) return;
    let cancelled = false;
    checkSession(sessionId)
      .then((s) => {
        if (!cancelled && s.phase1_complete) {
          router.replace(`/session/${sessionId}?step=analysis`);
        }
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [step, sessionId, router]);

  const handleResumeParsed = (parsed: ParsedResume) => {
    setParsedResume(parsed);
    // If JD is already filled (extension flow: JD → Resume → Info), advance to info.
    // Otherwise follow the normal flow: Resume → JD.
    goTo(jdText.trim() ? "info" : "jd");
  };

  // JD submitted → save to backend, store text locally, advance to next step.
  // In the extension flow the user lands directly on JD having skipped resume
  // upload, so we redirect them to "resume" next. In the normal flow they
  // already uploaded a resume (parsedResume is set) or have a master resume
  // saved, so we can go straight to "info".
  const handleJD = async (payload: JDPayload) => {
    if (!sessionId) return;
    setLoading(true);
    setJdText(payload.jd_text);
    try {
      await submitJD(sessionId, payload);

      let resumeData: ParsedResume | null = parsedResume;

      if (!resumeData) {
        try {
          const snapshot = await checkSession(sessionId);
          if (snapshot.resume_parsed) {
            resumeData = snapshot.resume_parsed;
          }
        } catch {
          // continue to profile import
        }
      }

      if (!resumeData && backendToken) {
        try {
          const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
          const res = await fetch(`${BASE}/api/profile/resume`, {
            headers: { Authorization: `Bearer ${backendToken}` },
          });
          if (res.ok) {
            const data = (await res.json()) as { raw_text?: string };
            if (data.raw_text?.trim()) {
              const result = await pasteResumeText(sessionId, data.raw_text);
              resumeData = result.parsed;
            }
          }
        } catch {
          // fall through to resume upload step
        }
      }

      if (resumeData) {
        setParsedResume(resumeData);
        goTo("info");
      } else {
        goTo("resume");
      }
    } finally {
      setLoading(false);
    }
  };

  // Info submitted → save then start analysis
  const handleUserInfo = async (info: UserInfoPayload) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      const handoff = getExtensionHandoff();
      const jdId = searchParams.get("jd_id") ?? handoff?.jd_id ?? undefined;
      await saveUserInfo(sessionId, info, jdId);
      sessionStorage.removeItem("smart_resume_session_id");
      router.replace(`/session/${sessionId}?step=analysis`);
    } finally {
      setLoading(false);
    }
  };

  const stepIndex = STEPS.indexOf(step);

  function handleWizardBack() {
    if (stepIndex <= 0) {
      router.push("/dashboard");
      return;
    }
    goTo(STEPS[stepIndex - 1]!);
  }

  return (
    <div className="min-h-screen bg-sr-bg text-sr-fg">
      <div className="max-w-2xl mx-auto px-6 py-12">

        <button
          type="button"
          onClick={handleWizardBack}
          className="inline-flex items-center gap-1.5 text-slate-600 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-300 text-sm mb-8 transition-colors"
        >
          ← Back
        </button>

        {/* Progress bar */}
        <div className="flex items-center gap-2 mb-10">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <button
                type="button"
                onClick={() => {
                  if (i < stepIndex) goTo(s);
                }}
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${
                  i < stepIndex
                    ? "bg-amber-400 text-slate-900 hover:bg-amber-300 cursor-pointer"
                    : i === stepIndex
                    ? "bg-amber-400 text-slate-900 ring-2 ring-amber-400/30"
                    : "bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-400 cursor-default"
                }`}
              >
                {i < stepIndex ? "✓" : i + 1}
              </button>
              <span
                className={`text-xs font-medium hidden sm:block ${
                  i === stepIndex
                    ? "text-slate-800 dark:text-slate-200"
                    : i < stepIndex
                    ? "text-slate-600 dark:text-slate-400"
                    : "text-slate-600 dark:text-slate-400 dark:text-slate-600"
                }`}
              >
                {STEP_LABELS[s]}
              </span>
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-px ${i < stepIndex ? "bg-amber-400" : "bg-slate-200 dark:bg-slate-800"}`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 sm:p-8">

          {/* ── Step 1: Upload Resume ───────────────────────────────────── */}
          {step === "resume" && !sessionId && (
            <div className="py-12 text-center">
              <div className="inline-block h-8 w-8 animate-spin rounded-full border-2 border-amber-400 border-t-transparent" />
              <p className="text-slate-600 dark:text-slate-400 text-sm mt-4">Starting your session…</p>
            </div>
          )}
          {step === "resume" && sessionId && (
            <div>
              <h1 className="text-xl font-bold mb-1">Upload your resume</h1>
              <p className="text-slate-600 dark:text-slate-400 text-sm mb-6">
                Upload a file, paste text, speak it, or reuse your saved master resume. Voice with
                live transcription is free in Chrome and Edge.
              </p>
              <ResumeUploader
                sessionId={sessionId}
                token={session?.backendAccessToken ?? undefined}
                onParsed={handleResumeParsed}
                hasMasterResume={hasMasterResume}
                onMasterResumeSaved={() => setHasMasterResume(true)}
              />
            </div>
          )}

          {/* ── Step 3: Job Description ─────────────────────────────────── */}
          {step === "jd" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Job description</h1>
              <p className="text-slate-600 dark:text-slate-400 text-sm mb-6">
                Paste the full job posting. TalioCV uses platform AI to extract ATS keywords
                and pre-fill your info from your resume.
              </p>
              <JDInput
                onSubmit={handleJD}
                loading={loading}
                initialJdText={jdText}
                jdId={searchParams.get("jd_id") ?? undefined}
                showCompletenessWarning={jdReviewRecommended}
                sourceUrl={jdSourceUrl}
              />
            </div>
          )}

          {/* ── Step 4: Your Info ───────────────────────────────────────── */}
          {step === "info" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Your information</h1>
              <p className="text-slate-600 dark:text-slate-400 text-sm mb-6">
                We pre-filled everything we found in your resume.
                Correct anything that looks wrong, then add your target role.
              </p>
              {infoHydrating && !parsedResume ? (
                <p className="text-slate-600 dark:text-slate-400 text-sm">Loading your resume details…</p>
              ) : (
                <UserInfoForm
                  onSubmit={handleUserInfo}
                  loading={loading}
                  parsedResume={parsedResume}
                  jdText={jdText}
                />
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function NewSessionPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-sr-bg flex items-center justify-center text-slate-600 dark:text-slate-400">
          Loading…
        </div>
      }
    >
      <NewSessionContent />
    </Suspense>
  );
}
