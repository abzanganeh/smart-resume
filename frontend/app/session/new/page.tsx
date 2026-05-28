"use client";

import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { ResumeUploader } from "@/components/wizard/ResumeUploader";
import { UserInfoForm } from "@/components/wizard/UserInfoForm";
import { JDInput } from "@/components/wizard/JDInput";
import ApiKeySettings from "@/components/wizard/ApiKeySettings";
import { createSession, saveUserInfo, submitJD, type JDPayload, type ParsedResume, type UserInfoPayload } from "@/lib/api";
import { getStoredKey } from "@/lib/keyStore";

const STEPS = ["resume", "info", "jd"] as const;
type Step = (typeof STEPS)[number];

const STEP_LABELS: Record<Step, string> = {
  resume: "Upload Resume",
  info: "Your Info",
  jd: "Job Description",
};

function NewSessionContent() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [step, setStep] = useState<Step>((searchParams.get("step") as Step) ?? "resume");
  const [, setParsedResume] = useState<ParsedResume | null>(null);
  const [loading, setLoading] = useState(false);
  const [provider, setProvider] = useState("openai");
  const [model, setModel] = useState("gpt-4o");

  // Create session on mount
  useEffect(() => {
    const existing = sessionStorage.getItem("smart_resume_session_id");
    if (existing) {
      setSessionId(existing);
    } else {
      createSession().then((r) => {
        setSessionId(r.session_id);
        sessionStorage.setItem("smart_resume_session_id", r.session_id);
      });
    }

    // Pre-fill provider/model from stored BYOK key if available
    const stored = getStoredKey();
    if (stored) {
      setProvider(stored.provider);
      setModel(stored.model);
    }
  }, []);

  const goTo = (s: Step) => {
    setStep(s);
    router.replace(`/session/new?step=${s}`);
  };

  const handleResumeParsed = (parsed: ParsedResume) => {
    setParsedResume(parsed);
    goTo("info");
  };

  const handleUserInfo = async (info: UserInfoPayload) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      await saveUserInfo(sessionId, info);
      goTo("jd");
    } finally {
      setLoading(false);
    }
  };

  const handleJD = async (payload: JDPayload) => {
    if (!sessionId) return;
    setLoading(true);
    try {
      // provider/model go in the body so the session records them;
      // the API key goes in headers automatically via byokHeaders()
      await submitJD(sessionId, { ...payload, provider, model });
      router.push(`/session/${sessionId}?step=keywords`);
    } finally {
      setLoading(false);
    }
  };

  const stepIndex = STEPS.indexOf(step);

  return (
    <div className="min-h-screen bg-slate-950 text-white">
      <div className="max-w-2xl mx-auto px-6 py-16">
        {/* Progress */}
        <div className="flex items-center gap-2 mb-10">
          {STEPS.map((s, i) => (
            <div key={s} className="flex items-center gap-2 flex-1">
              <div
                className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold shrink-0
                ${i < stepIndex ? "bg-amber-400 text-slate-900" : i === stepIndex ? "bg-amber-400 text-slate-900 ring-2 ring-amber-400/30" : "bg-slate-800 text-slate-500"}`}
              >
                {i < stepIndex ? "✓" : i + 1}
              </div>
              <span className={`text-xs font-medium ${i === stepIndex ? "text-slate-200" : "text-slate-500"}`}>
                {STEP_LABELS[s]}
              </span>
              {i < STEPS.length - 1 && (
                <div className={`flex-1 h-px ${i < stepIndex ? "bg-amber-400" : "bg-slate-800"}`} />
              )}
            </div>
          ))}
        </div>

        {/* Step content */}
        <div className="bg-slate-900 border border-slate-800 rounded-2xl p-8">
          {step === "resume" && sessionId && (
            <div>
              <h1 className="text-xl font-bold mb-2">Upload your resume</h1>
              <p className="text-slate-400 text-sm mb-6">Supports PDF, DOCX, and plain text. Max 5MB.</p>
              <ResumeUploader sessionId={sessionId} onParsed={handleResumeParsed} />
            </div>
          )}

          {step === "info" && (
            <div>
              <h1 className="text-xl font-bold mb-2">Your information</h1>
              <p className="text-slate-400 text-sm mb-6">This helps the agent tailor the resume correctly.</p>
              <UserInfoForm onSubmit={handleUserInfo} loading={loading} />
            </div>
          )}

          {step === "jd" && (
            <div>
              <h1 className="text-xl font-bold mb-2">Job description</h1>
              <p className="text-slate-400 text-sm mb-4">
                Paste the job posting. The agent will extract every ATS keyword.
              </p>

              {/* BYOK provider + key selection */}
              <div className="mb-5">
                <ApiKeySettings
                  onChange={(p, m) => {
                    setProvider(p);
                    setModel(m);
                  }}
                />
              </div>

              <JDInput
                onSubmit={handleJD}
                selectedProvider={provider}
                selectedModel={model}
                loading={loading}
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
