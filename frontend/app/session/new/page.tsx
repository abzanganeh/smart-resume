"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ResumeUploader } from "@/components/wizard/ResumeUploader";
import { UserInfoForm } from "@/components/wizard/UserInfoForm";
import { JDInput } from "@/components/wizard/JDInput";
import ProviderSetup from "@/components/wizard/ProviderSetup";
import {
  createSession,
  saveUserInfo,
  submitJD,
  type JDPayload,
  type ParsedResume,
  type UserInfoPayload,
} from "@/lib/api";
import { getStoredKey } from "@/lib/keyStore";

// New order: AI → Resume → Job Description → Your Info
const STEPS = ["ai", "resume", "jd", "info"] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  ai:     "Choose AI",
  resume: "Upload Resume",
  jd:     "Job Description",
  info:   "Your Info",
};

function NewSessionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [step, setStep] = useState<Step>((searchParams.get("step") as Step) ?? "ai");

  // Carry forward between steps
  const [parsedResume, setParsedResume] = useState<ParsedResume | null>(null);
  const [jdText, setJdText] = useState("");

  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o");
  const [aiReady, setAiReady] = useState(false);

  useEffect(() => {
    async function initSession() {
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
      try {
        const r = await createSession();
        setSessionId(r.session_id);
        sessionStorage.setItem("smart_resume_session_id", r.session_id);
      } catch {
        // backend not running — will show error when user tries to upload
      }
    }

    initSession();

    const stored = getStoredKey();
    if (stored) {
      setProvider(stored.provider);
      setModel(stored.model);
      setAiReady(true);
    }
  }, []);

  const goTo = (s: Step) => {
    setStep(s);
    router.replace(`/session/new?step=${s}`);
  };

  const handleAiComplete = (p: string, m: string) => {
    setProvider(p);
    setModel(m);
    setAiReady(true);
    goTo("resume");
  };

  const handleResumeParsed = (parsed: ParsedResume) => {
    setParsedResume(parsed);
    goTo("jd");
  };

  // JD submitted → save to backend, store text locally, advance to info
  const handleJD = async (payload: JDPayload) => {
    if (!sessionId) return;
    setLoading(true);
    setJdText(payload.jd_text);
    try {
      await submitJD(sessionId, { ...payload, provider, model });
      goTo("info");
    } finally {
      setLoading(false);
    }
  };

  // Info submitted → save then start analysis
  const handleUserInfo = async (info: UserInfoPayload) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await saveUserInfo(sessionId, info);
      router.push(`/session/${sessionId}?step=keywords`);
    } finally {
      setLoading(false);
    }
  };

  const stepIndex = STEPS.indexOf(step);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-2xl mx-auto px-6 py-12">

        <a
          href="/"
          className="inline-flex items-center gap-1.5 text-slate-500 hover:text-slate-300 text-sm mb-8 transition-colors"
        >
          ← Back
        </a>

        {/* Progress bar */}
        <div className="flex items-center gap-2 mb-10">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <button
                type="button"
                onClick={() => {
                  if (i < stepIndex || s === "ai") goTo(s);
                }}
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0 transition-colors ${
                  i < stepIndex
                    ? "bg-amber-400 text-slate-900 hover:bg-amber-300 cursor-pointer"
                    : i === stepIndex
                    ? s === "ai"
                      ? "bg-violet-600 text-white ring-2 ring-violet-500/40"
                      : "bg-amber-400 text-slate-900 ring-2 ring-amber-400/30"
                    : "bg-slate-800 text-slate-500 cursor-default"
                }`}
              >
                {i < stepIndex ? "✓" : i + 1}
              </button>
              <span
                className={`text-xs font-medium hidden sm:block ${
                  i === stepIndex
                    ? "text-slate-200"
                    : i < stepIndex
                    ? "text-slate-400"
                    : "text-slate-600"
                }`}
              >
                {STEP_LABELS[s]}
              </span>
              {i < STEPS.length - 1 && (
                <div
                  className={`flex-1 h-px ${i < stepIndex ? "bg-amber-400" : "bg-slate-800"}`}
                />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 sm:p-8">

          {/* ── Step 1: Choose AI ───────────────────────────────────────── */}
          {step === "ai" && (
            <div>
              <div className="mb-6">
                <h1 className="text-xl font-bold mb-1">Choose your AI provider</h1>
                <p className="text-slate-400 text-sm">
                  This app uses{" "}
                  <strong className="text-slate-200">your own API key</strong> — we never
                  pay for or store your AI calls. Pick a free option if you don't have a key yet.
                </p>
              </div>
              <ProviderSetup onComplete={handleAiComplete} />
            </div>
          )}

          {/* ── Step 2: Upload Resume ───────────────────────────────────── */}
          {step === "resume" && sessionId && (
            <div>
              <h1 className="text-xl font-bold mb-1">Upload your resume</h1>
              <p className="text-slate-400 text-sm mb-6">
                Supports PDF, DOCX, and plain text. Max 5 MB.
              </p>
              <ResumeUploader sessionId={sessionId} onParsed={handleResumeParsed} />
            </div>
          )}

          {/* ── Step 3: Job Description ─────────────────────────────────── */}
          {step === "jd" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Job description</h1>
              <p className="text-slate-400 text-sm mb-1">
                Paste the full job posting. We'll extract every ATS keyword and
                then pre-fill your info from what's already in your resume.
              </p>
              <div className="flex items-center gap-2 mb-6">
                <span className="text-xs text-slate-500">Using:</span>
                <span className="text-xs font-medium text-slate-300 bg-slate-800 border border-slate-700 rounded px-2 py-0.5">
                  {provider} / {model}
                </span>
                <button
                  type="button"
                  onClick={() => goTo("ai")}
                  className="text-xs text-violet-400 hover:text-violet-300 transition-colors"
                >
                  change
                </button>
              </div>
              <JDInput
                onSubmit={handleJD}
                selectedProvider={provider}
                selectedModel={model}
                loading={loading}
              />
            </div>
          )}

          {/* ── Step 4: Your Info ───────────────────────────────────────── */}
          {step === "info" && (
            <div>
              <h1 className="text-xl font-bold mb-1">Your information</h1>
              <p className="text-slate-400 text-sm mb-6">
                We pre-filled everything we found in your resume.
                Correct anything that looks wrong, then add your target role.
              </p>
              <UserInfoForm
                onSubmit={handleUserInfo}
                loading={loading}
                parsedResume={parsedResume}
                jdText={jdText}
              />
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
        <div className="min-h-screen bg-slate-950 flex items-center justify-center text-slate-400">
          Loading…
        </div>
      }
    >
      <NewSessionContent />
    </Suspense>
  );
}
