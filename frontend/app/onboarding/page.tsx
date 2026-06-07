/**
 * Onboarding — first-run flow after registration.
 */
"use client"

import { useEffect, useState, useTransition } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import { useSession } from "next-auth/react"
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Key,
  Loader2,
  Mic,
  Sparkles,
  Upload,
  Zap,
} from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { patchOnboarding } from "@/lib/auth/api"
import { needsOnboarding, postOnboardingDestination } from "@/lib/auth/onboarding"
import { clsx } from "clsx"

type AiChoice = "platform" | "byok"

const CREDIT_COSTS = [
  { action: "Tailor resume to a job", cost: "1 credit" },
  { action: "Coached interview (Story Mode)", cost: "1 credit / session" },
  { action: "Story coaching (while building a resume)", cost: "1 credit / build" },
  { action: "ATS score recalculation", cost: "1 credit" },
  { action: "Tell your story (Chrome/Edge voice)", cost: "Free" },
  { action: "Cover letter generation", cost: "1 credit" },
]

const BYOK_PROVIDERS = [
  "OpenAI (GPT-4o, etc.)",
  "Anthropic Claude",
  "Google Gemini",
  "OpenRouter (incl. free models)",
  "Ollama (self-hosted — your machine or server)",
]

function OnboardingAiStep({
  choice,
  onChange,
}: {
  choice: AiChoice
  onChange: (c: AiChoice) => void
}) {
  return (
    <div className="space-y-5 text-left max-w-md mx-auto">
      <p className="text-slate-400 text-sm text-center leading-relaxed">
        Choose how AI features are powered. You can change this any time when starting a session.
      </p>

      <button
        type="button"
        onClick={() => onChange("platform")}
        className={clsx(
          "w-full rounded-xl border p-4 text-left transition-all",
          choice === "platform"
            ? "border-amber-400/60 bg-amber-400/5 ring-1 ring-amber-400/30"
            : "border-slate-700 bg-slate-800/40 hover:border-slate-600",
        )}
      >
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-4 h-4 text-amber-400" />
          <span className="font-semibold text-slate-100 text-sm">Use Smart Resume AI</span>
          <span className="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700">
            Recommended
          </span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          We run the AI for you. Your account includes <strong className="text-slate-200">6 free credits</strong> to
          get started — no API key needed.
        </p>
      </button>

      {choice === "platform" && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-2">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">What credits buy</p>
          <ul className="space-y-1.5">
            {CREDIT_COSTS.map((row) => (
              <li key={row.action} className="flex justify-between gap-3 text-xs">
                <span className="text-slate-400">{row.action}</span>
                <span className="text-slate-200 font-medium shrink-0">{row.cost}</span>
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-slate-500 pt-1">
            Subscribers get unlimited resume builds. Upgrade anytime from Billing.
          </p>
        </div>
      )}

      <button
        type="button"
        onClick={() => onChange("byok")}
        className={clsx(
          "w-full rounded-xl border p-4 text-left transition-all",
          choice === "byok"
            ? "border-indigo-400/60 bg-indigo-400/5 ring-1 ring-indigo-400/30"
            : "border-slate-700 bg-slate-800/40 hover:border-slate-600",
        )}
      >
        <div className="flex items-center gap-2 mb-2">
          <Key className="w-4 h-4 text-indigo-400" />
          <span className="font-semibold text-slate-100 text-sm">Bring your own API key (BYOK)</span>
        </div>
        <p className="text-xs text-slate-400 leading-relaxed">
          Use your own LLM account. You pay the provider directly; Smart Resume orchestrates the pipeline.
        </p>
      </button>

      {choice === "byok" && (
        <div className="rounded-xl border border-slate-700 bg-slate-900/60 p-4 space-y-3">
          <p className="text-xs font-semibold text-slate-300 uppercase tracking-wide">Supported providers</p>
          <ul className="space-y-1">
            {BYOK_PROVIDERS.map((p) => (
              <li key={p} className="flex items-center gap-2 text-xs text-slate-400">
                <CheckCircle2 className="w-3 h-3 text-indigo-400 shrink-0" />
                {p}
              </li>
            ))}
          </ul>
          <p className="text-[11px] text-slate-500 leading-relaxed">
            Add your key when you start your first tailoring session (step 3 of the session wizard).
            Your key stays in your browser only — we never store it on our servers.
          </p>
          <Link
            href="/session/new?step=ai"
            className="inline-flex items-center gap-1 text-xs text-indigo-400 hover:text-indigo-300 font-medium"
          >
            Set up API key now <ArrowRight className="w-3 h-3" />
          </Link>
        </div>
      )}
    </div>
  )
}

const STEPS = [
  {
    title: "Welcome to Smart Resume",
    subtitle: "Let's get your account ready in a few quick steps.",
    icon: Sparkles,
    bodyKey: "welcome" as const,
    cta: "Continue",
  },
  {
    title: "How do you want to use AI?",
    subtitle: "Pick one — you can switch later.",
    icon: Zap,
    bodyKey: "ai" as const,
    cta: "Continue",
  },
  {
    title: "Build your master resume",
    subtitle: "Generate it by speaking, or upload an existing file.",
    icon: Mic,
    bodyKey: "master" as const,
    cta: "Generate or upload resume",
  },
  {
    title: "You're all set!",
    subtitle: "Your dashboard is ready whenever you need it.",
    icon: FileText,
    bodyKey: "done" as const,
    cta: "Go to dashboard",
  },
] as const

function initialStepFromUser(user: { onboarding_ai_choice?: string | null } | undefined): number {
  if (user?.onboarding_ai_choice) return 2
  return 0
}

export default function OnboardingPage() {
  const router = useRouter()
  const { session, status } = useRequireAuth("/onboarding")
  const { update } = useSession()
  const [step, setStep] = useState(0)
  const [aiChoice, setAiChoice] = useState<AiChoice>("platform")
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const [initialized, setInitialized] = useState(false)

  useEffect(() => {
    if (status !== "authenticated" || !session?.backendUser) return

    if (!needsOnboarding(session.backendUser)) {
      router.replace(postOnboardingDestination(session.backendUser))
      return
    }

    if (!initialized) {
      const saved = session.backendUser.onboarding_ai_choice
      if (saved === "platform" || saved === "byok") {
        setAiChoice(saved)
      }
      setStep(initialStepFromUser(session.backendUser))
      setInitialized(true)
    }
  }, [session, status, router, initialized])

  async function syncSession(user: Awaited<ReturnType<typeof patchOnboarding>>) {
    await update({ backendUser: user })
  }

  async function saveAiChoice(choice: AiChoice) {
    const token = session?.backendAccessToken
    if (!token) throw new Error("Not signed in")
    const user = await patchOnboarding(token, { ai_choice: choice })
    await syncSession(user)
  }

  async function completeOnboarding(choice: AiChoice) {
    const token = session?.backendAccessToken
    if (!token) throw new Error("Not signed in")
    const user = await patchOnboarding(token, { ai_choice: choice, complete: true })
    await syncSession(user)
    router.replace(postOnboardingDestination(user))
  }

  if (status === "loading" || !session) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const name = session.backendUser?.display_name ?? session.user?.name ?? "there"
  const current = STEPS[step]
  const Icon = current.icon
  const isLast = step === STEPS.length - 1
  const isMasterStep = step === 2

  function handlePrimary() {
    setError(null)
    startTransition(async () => {
      try {
        if (step === 1) {
          await saveAiChoice(aiChoice)
          setStep((s) => s + 1)
          return
        }
        if (isMasterStep) {
          await saveAiChoice(aiChoice)
          router.push("/profile?mode=story&from=onboarding")
          return
        }
        if (isLast) {
          await completeOnboarding(aiChoice)
          return
        }
        setStep((s) => s + 1)
      } catch (err: unknown) {
        setError((err as Error).message || "Something went wrong. Please try again.")
      }
    })
  }

  function handleSkipMaster() {
    setError(null)
    startTransition(async () => {
      try {
        await completeOnboarding(aiChoice)
      } catch (err: unknown) {
        setError((err as Error).message || "Something went wrong. Please try again.")
      }
    })
  }

  function renderBody() {
    switch (current.bodyKey) {
      case "welcome":
        return (
          <>
            <p className="text-slate-400 leading-relaxed mb-6">
              Smart Resume tailors your master resume to every job description with ATS keyword
              analysis and evidence-based quality rules. You can{" "}
              <strong className="text-slate-200">speak your career story</strong>, use a coached
              AI interview, or upload an existing resume.
            </p>
            <ul className="text-sm text-slate-400 space-y-2 text-left max-w-md mx-auto">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                One master resume — unlimited tailored versions
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                Voice story mode + AI coached interview
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                6 free credits included — no credit card required
              </li>
            </ul>
          </>
        )
      case "ai":
        return <OnboardingAiStep choice={aiChoice} onChange={setAiChoice} />
      case "master":
        return (
          <div className="space-y-4 text-left max-w-md mx-auto">
            <p className="text-slate-400 text-sm leading-relaxed text-center">
              Your master resume is the foundation for every tailored version. Choose whichever
              path fits you best:
            </p>
            <ul className="space-y-3">
              <li className="flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-800/40 p-3">
                <Mic className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-200">Tell your story</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    Record your career by voice, with optional AI coaching after each segment.
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-800/40 p-3">
                <Sparkles className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-200">Coached interview</p>
                  <p className="text-xs text-slate-400 mt-0.5">
                    The AI asks structured career questions — you answer by voice or text.
                  </p>
                </div>
              </li>
              <li className="flex items-start gap-3 rounded-xl border border-slate-700 bg-slate-800/40 p-3">
                <Upload className="w-4 h-4 text-slate-300 shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-medium text-slate-200">Upload a file</p>
                  <p className="text-xs text-slate-400 mt-0.5">PDF, DOCX, or plain text — max 5 MB.</p>
                </div>
              </li>
            </ul>
            <p className="text-xs text-slate-500 text-center">
              Skip for now — your dashboard will prompt you to build one when you&apos;re ready.
            </p>
          </div>
        )
      case "done":
        return (
          <div className="space-y-4 max-w-md mx-auto">
            <p className="text-slate-400 leading-relaxed">
              Track every resume you build, monitor ATS scores over time, and manage your
              subscription from the dashboard.
            </p>
            <Link
              href="/session/new"
              className="flex items-center justify-center gap-2 w-full rounded-xl border border-slate-700 hover:border-amber-400/50 bg-slate-800/40 hover:bg-slate-800 px-4 py-3 text-sm text-slate-200 transition-colors"
            >
              <FileText className="w-4 h-4 text-amber-400" />
              Tailor your first resume now
            </Link>
          </div>
        )
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-lg text-center">
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={clsx(
                "h-1.5 rounded-full transition-all",
                i === step ? "w-8 bg-amber-400" : i < step ? "w-4 bg-amber-400/50" : "w-4 bg-slate-700",
              )}
            />
          ))}
        </div>

        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-400/10 border border-amber-400/20 mb-6">
          <Icon className="w-8 h-8 text-amber-400" />
        </div>

        <p className="text-xs font-semibold uppercase tracking-widest text-amber-400/80 mb-2">
          Step {step + 1} of {STEPS.length}
        </p>
        <h1 className="text-3xl font-bold text-white mb-2">
          {step === 0 ? `Welcome, ${name}!` : current.title}
        </h1>
        <p className="text-slate-400 mb-8">{current.subtitle}</p>

        <div className="mb-10">{renderBody()}</div>

        {error && (
          <p className="mb-4 text-sm text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          {step > 0 && (
            <button
              type="button"
              disabled={isPending}
              onClick={() => setStep((s) => s - 1)}
              className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 px-4 py-2.5 disabled:opacity-50"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
          )}
          <button
            type="button"
            disabled={isPending}
            onClick={handlePrimary}
            className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors disabled:opacity-60"
          >
            {isPending ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Saving…
              </>
            ) : (
              <>
                {current.cta}
                <ArrowRight className="w-4 h-4" />
              </>
            )}
          </button>
          {isMasterStep && (
            <button
              type="button"
              disabled={isPending}
              onClick={handleSkipMaster}
              className="text-sm text-slate-500 hover:text-slate-300 underline underline-offset-4 disabled:opacity-50"
            >
              Skip for now
            </button>
          )}
        </div>
      </div>
    </main>
  )
}
