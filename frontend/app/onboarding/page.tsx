"use client"

/**
 * Onboarding — first-run flow after registration.
 *
 * All five steps are intro-only: setup (master resume, job titles, tailoring)
 * happens from the dashboard and dedicated routes after onboarding completes.
 */
import { Suspense, useEffect, useRef, useState, useTransition } from "react"
import Link from "next/link"
import { useRouter, useSearchParams } from "next/navigation"
import { useSession } from "next-auth/react"
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Loader2,
  Mic,
  Search,
  Sparkles,
  Zap,
} from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { PRODUCT_NAME } from "@/lib/brand"
import { friendlyAuthError } from "@/lib/auth/errors"
import { fetchMe, patchOnboarding } from "@/lib/auth/api"
import {
  needsOnboarding,
  parseOnboardingStepParam,
  postOnboardingDestination,
  resolveOnboardingStepIndex,
} from "@/lib/auth/onboarding"
import {
  FREE_TIER_CREDIT_ACTIONS,
  FREE_TIER_NON_CREDIT_LIMITS_COPY,
  FREE_TIER_STARTING_CREDITS,
  VOICE_AVAILABILITY_COPY,
} from "@/lib/freeTier"
import { clsx } from "clsx"

type AiChoice = "platform"

function OnboardingAiStep() {
  return (
    <div className="space-y-5 text-left max-w-md mx-auto">
      <p className="text-slate-600 dark:text-slate-400 text-sm text-center leading-relaxed">
        {PRODUCT_NAME} runs the AI for you. Free accounts start with{" "}
        <strong className="text-slate-900 dark:text-slate-200">
          {FREE_TIER_STARTING_CREDITS} credits
        </strong>
        ; subscribers use monthly plan limits instead.
      </p>

      <div className="rounded-xl border border-amber-400/60 bg-amber-500/5 dark:bg-amber-400/5 ring-1 ring-amber-400/30 p-4">
        <div className="flex items-center gap-2 mb-2">
          <Zap className="w-4 h-4 text-amber-700 dark:text-amber-400" />
          <span className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
            {PRODUCT_NAME} AI
          </span>
          <span className="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-50 dark:bg-emerald-900/60 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-700">
            Included
          </span>
        </div>
        <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          No API key needed — platform AI is included. Most items below cost one credit;
          story generate and save are free the first time.
        </p>
      </div>

      <div className="rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/60 p-4 space-y-2">
        <p className="text-xs font-semibold text-slate-700 dark:text-slate-300 uppercase tracking-wide">
          What credits buy (free tier)
        </p>
        <ul className="space-y-1.5">
          {FREE_TIER_CREDIT_ACTIONS.map((row) => (
            <li key={row.action} className="flex justify-between gap-3 text-xs">
              <span className="text-slate-600 dark:text-slate-400">{row.action}</span>
              <span className="text-slate-900 dark:text-slate-200 font-medium shrink-0">
                {row.cost}
              </span>
            </li>
          ))}
        </ul>
        <p className="text-xs text-slate-600 dark:text-slate-400 pt-1">
          {FREE_TIER_NON_CREDIT_LIMITS_COPY} {VOICE_AVAILABILITY_COPY} You can also upload or
          paste a resume. After your master resume, {PRODUCT_NAME} suggests job titles to search
          our company job corpus. Fit analysis and expanded search need a paid plan.
        </p>
      </div>
    </div>
  )
}

const STEPS = [
  {
    title: `Welcome to ${PRODUCT_NAME}`,
    subtitle: "Let's get your account ready in a few quick steps.",
    icon: Sparkles,
    bodyKey: "welcome" as const,
    cta: "Continue",
  },
  {
    title: "How do you want to use AI?",
    subtitle: "Platform AI is included — here's what your free credits cover.",
    icon: Zap,
    bodyKey: "ai" as const,
    cta: "Continue",
  },
  {
    title: "Build your master resume",
    subtitle: "One resume you maintain — tailored versions for every job.",
    icon: Mic,
    bodyKey: "master" as const,
    cta: "Continue",
  },
  {
    title: "Which roles should we search for?",
    subtitle: "We'll suggest titles from your resume — search our company job corpus for free.",
    icon: Search,
    bodyKey: "jobTitles" as const,
    cta: "Continue",
  },
  {
    title: "You're all set!",
    subtitle: "Your dashboard is ready whenever you need it.",
    icon: FileText,
    bodyKey: "done" as const,
    cta: "Go to dashboard",
  },
] as const

function OnboardingPageContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const { session, status } = useRequireAuth("/onboarding")
  const { update } = useSession()
  const [step, setStep] = useState(0)
  const [aiChoice, setAiChoice] = useState<AiChoice>("platform")
  const [error, setError] = useState<string | null>(null)
  const [isPending, startTransition] = useTransition()
  const [hydrated, setHydrated] = useState(false)
  const updateRef = useRef(update)
  useEffect(() => {
    updateRef.current = update
  }, [update])

  const token = session?.backendAccessToken
  const urlStepParam = searchParams.get("step")

  useEffect(() => {
    if (status === "loading" || !session) return

    if (status === "authenticated" && !token) {
      setError(
        friendlyAuthError(session.error ?? "missing_api_token"),
      )
      setHydrated(true)
      return
    }

    if (!token) return
    if (hydrated && !urlStepParam) return

    let cancelled = false

    void (async () => {
      try {
        const user = await fetchMe(token)
        if (cancelled) return

        void updateRef.current({ backendUser: user })

        if (!needsOnboarding(user)) {
          router.replace(postOnboardingDestination(user))
          return
        }

        const urlStep = parseOnboardingStepParam(urlStepParam)
        const stepIndex = resolveOnboardingStepIndex(user, {
          urlStepIndex: urlStep,
        })

        if (user.onboarding_ai_choice === "platform") {
          setAiChoice("platform")
        }
        setStep(Math.max(0, stepIndex))
      } catch (err: unknown) {
        if (!cancelled) {
          setError((err as Error).message || "Could not load onboarding progress.")
        }
      } finally {
        if (!cancelled) setHydrated(true)
      }
    })()

    return () => {
      cancelled = true
    }
  }, [status, token, urlStepParam, hydrated, router, session])

  async function syncSession(user: Awaited<ReturnType<typeof patchOnboarding>>) {
    await update({ backendUser: user })
  }

  async function saveAiChoice(choice: AiChoice) {
    const accessToken = session?.backendAccessToken
    if (!accessToken) throw new Error("Not signed in")
    const user = await patchOnboarding(accessToken, { ai_choice: choice })
    await syncSession(user)
  }

  async function completeOnboarding(choice: AiChoice) {
    const accessToken = session?.backendAccessToken
    if (!accessToken) throw new Error("Not signed in")
    const user = await patchOnboarding(accessToken, { ai_choice: choice, complete: true })
    await syncSession(user)
    window.location.assign(postOnboardingDestination(user))
  }

  if (status === "loading" || !session || !hydrated) {
    return (
      <div className="min-h-screen bg-sr-bg flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const name = session.backendUser?.display_name ?? session.user?.name ?? "there"
  const current = STEPS[step]
  const Icon = current.icon
  const isLast = step === STEPS.length - 1

  function handlePrimary() {
    setError(null)
    startTransition(async () => {
      try {
        if (step === 1) {
          await saveAiChoice(aiChoice)
          setStep((s) => s + 1)
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

  function renderBody() {
    switch (current.bodyKey) {
      case "welcome":
        return (
          <>
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed mb-6">
              {PRODUCT_NAME} tailors your master resume to every job description with ATS keyword
              analysis and evidence-based quality rules. Upload an existing resume or paste text
              to get started on the free plan.
            </p>
            <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-2 text-left max-w-md mx-auto">
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
                One master resume — tailored versions per job
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
                Platform AI included — no API key required
              </li>
              <li className="flex items-start gap-2">
                <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
                {FREE_TIER_STARTING_CREDITS} free credits on signup — no credit card required
              </li>
            </ul>
          </>
        )
      case "ai":
        return <OnboardingAiStep />
      case "master":
        return (
          <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-2 text-left max-w-md mx-auto">
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              Upload a file, paste text, or speak your career story on your profile
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              We chunk and embed it once — every tailored resume draws from it
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              Job-title suggestions and fit scores use this resume after you add it
            </li>
          </ul>
        )
      case "jobTitles":
        return (
          <ul className="text-sm text-slate-600 dark:text-slate-400 space-y-2 text-left max-w-md mx-auto">
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              {PRODUCT_NAME} ranks realistic titles from your master resume
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              Pick up to 12 target roles to search our company job corpus
            </li>
            <li className="flex items-start gap-2">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 dark:text-emerald-400 shrink-0 mt-0.5" />
              Expanded search and fit scoring are available on paid plans
            </li>
          </ul>
        )
      case "done":
        return (
          <div className="space-y-4 max-w-md mx-auto">
            <p className="text-slate-600 dark:text-slate-400 leading-relaxed">
              Track every resume you build, monitor ATS scores over time, and manage your
              subscription from the dashboard.
            </p>
            <Link
              href="/profile"
              className="flex items-center justify-center gap-2 w-full rounded-xl border border-slate-300 dark:border-slate-700 hover:border-amber-400/50 bg-slate-100/40 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-3 text-sm text-slate-800 dark:text-slate-200 transition-colors"
            >
              <FileText className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              Add your master resume
            </Link>
            <Link
              href="/jobs/setup"
              className="flex items-center justify-center gap-2 w-full rounded-xl border border-slate-300 dark:border-slate-700 hover:border-amber-400/50 bg-slate-100/40 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-3 text-sm text-slate-800 dark:text-slate-200 transition-colors"
            >
              <Search className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              Choose job titles to search
            </Link>
            <Link
              href="/session/new"
              className="flex items-center justify-center gap-2 w-full rounded-xl border border-slate-300 dark:border-slate-700 hover:border-amber-400/50 bg-slate-100/40 dark:bg-slate-800/40 hover:bg-slate-100 dark:hover:bg-slate-800 px-4 py-3 text-sm text-slate-800 dark:text-slate-200 transition-colors"
            >
              <FileText className="w-4 h-4 text-amber-700 dark:text-amber-400" />
              Tailor your first resume now
            </Link>
          </div>
        )
    }
  }

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-lg text-center">
        <div className="flex items-center justify-center gap-2 mb-8">
          {STEPS.map((_, i) => (
            <div
              key={i}
              className={clsx(
                "h-1.5 rounded-full transition-all",
                i === step ? "w-8 bg-amber-400" : i < step ? "w-4 bg-amber-500/50 dark:bg-amber-400/50" : "w-4 bg-slate-200 dark:bg-slate-700",
              )}
            />
          ))}
        </div>

        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-500/10 dark:bg-amber-400/10 border border-amber-400/20 mb-6">
          <Icon className="w-8 h-8 text-amber-700 dark:text-amber-400" />
        </div>

        <p className="text-xs font-semibold uppercase tracking-widest text-amber-700 dark:text-amber-400/80 mb-2">
          Step {step + 1} of {STEPS.length}
        </p>
        <h1 className="text-3xl font-bold text-slate-900 dark:text-white mb-2">
          {step === 0 ? `Welcome, ${name}!` : current.title}
        </h1>
        <p className="text-slate-600 dark:text-slate-400 mb-8">{current.subtitle}</p>

        <div className="mb-10">{renderBody()}</div>

        {error && (
          <p className="mb-4 text-sm text-red-700 dark:text-red-400" role="alert">
            {error}
          </p>
        )}

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          {step > 0 && (
            <button
              type="button"
              disabled={isPending}
              onClick={() => setStep((s) => s - 1)}
              className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 px-4 py-2.5 disabled:opacity-50"
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
        </div>
      </div>
    </main>
  )
}

export default function OnboardingPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-sr-bg flex items-center justify-center">
          <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
        </div>
      }
    >
      <OnboardingPageContent />
    </Suspense>
  )
}
