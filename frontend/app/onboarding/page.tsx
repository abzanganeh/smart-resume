/**
 * Onboarding — 3-step first-run flow (Step 28 / P3 completion).
 */
"use client"

import { useState } from "react"
import Link from "next/link"
import { useRouter } from "next/navigation"
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  FileText,
  Sparkles,
  Upload,
} from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"
import { clsx } from "clsx"

const STEPS = [
  {
    title: "Welcome to Smart Resume",
    subtitle: "Let's get your account ready in three quick steps.",
    body: (
      <>
        <p className="text-slate-400 leading-relaxed mb-6">
          Smart Resume tailors your master resume to every job description with
          ATS keyword analysis and evidence-based quality rules. Start by
          uploading the resume you want to reuse across applications.
        </p>
        <ul className="text-sm text-slate-400 space-y-2 text-left max-w-md mx-auto">
          <li className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            One master resume — unlimited tailored versions
          </li>
          <li className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ATS score tracking on every build
          </li>
          <li className="flex items-start gap-2">
            <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            Cover letters and job fit analysis included
          </li>
        </ul>
      </>
    ),
    cta: "Upload your master resume",
    href: "/profile",
    icon: Upload,
  },
  {
    title: "Tailor your first resume",
    subtitle: "Paste a job description and run the agent pipeline.",
    body: (
      <p className="text-slate-400 leading-relaxed max-w-md mx-auto">
        Create a new session, paste the job description you&apos;re targeting,
        and let the four-phase agent extract keywords, audit gaps, rewrite your
        resume, and score it for ATS compatibility.
      </p>
    ),
    cta: "Start tailoring",
    href: "/session/new",
    icon: FileText,
  },
  {
    title: "You're all set!",
    subtitle: "Your dashboard is ready whenever you need it.",
    body: (
      <p className="text-slate-400 leading-relaxed max-w-md mx-auto">
        Track every resume you build, monitor ATS scores over time, and manage
        your subscription from the dashboard. You can always upload an updated
        master resume from your profile.
      </p>
    ),
    cta: "Go to dashboard",
    href: "/dashboard",
    icon: Sparkles,
  },
] as const

export default function OnboardingPage() {
  const router = useRouter()
  const { session, status } = useRequireAuth("/onboarding")
  const [step, setStep] = useState(0)

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

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-lg text-center">
        {/* Step indicator */}
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

        <div className="mb-10">{current.body}</div>

        <div className="flex flex-col sm:flex-row items-center justify-center gap-3">
          {step > 0 && (
            <button
              type="button"
              onClick={() => setStep((s) => s - 1)}
              className="inline-flex items-center gap-2 text-sm text-slate-400 hover:text-slate-200 px-4 py-2.5"
            >
              <ArrowLeft className="w-4 h-4" /> Back
            </button>
          )}
          {isLast ? (
            <Link
              href={current.href}
              className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors"
            >
              {current.cta}
              <ArrowRight className="w-4 h-4" />
            </Link>
          ) : (
            <button
              type="button"
              onClick={() => {
                if (step === 0 || step === 1) {
                  router.push(current.href)
                } else {
                  setStep((s) => s + 1)
                }
              }}
              className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors"
            >
              {current.cta}
              <ArrowRight className="w-4 h-4" />
            </button>
          )}
          {!isLast && (
            <button
              type="button"
              onClick={() => setStep((s) => s + 1)}
              className="text-sm text-slate-500 hover:text-slate-300 underline underline-offset-4"
            >
              Skip for now
            </button>
          )}
        </div>

        {step < STEPS.length - 1 && (
          <Link
            href="/dashboard"
            className="inline-block mt-8 text-sm text-slate-500 hover:text-slate-300 underline underline-offset-4"
          >
            Go to dashboard →
          </Link>
        )}
      </div>
    </main>
  )
}
