/**
 * Onboarding page — placeholder (P7 will flesh this out fully).
 *
 * Shown to users on their first login via the /auth redirect logic.
 * Guards the route so only authenticated users can reach it (the proxy
 * also enforces this at the edge, but we guard client-side for consistency).
 */
"use client"

import Link from "next/link"
import { ArrowRight, FileText, Settings, Sparkles } from "lucide-react"
import { useRequireAuth } from "@/lib/auth/guards"

export default function OnboardingPage() {
  const { session, status } = useRequireAuth("/onboarding")

  if (status === "loading" || !session) {
    return (
      <div className="min-h-screen bg-slate-950 flex items-center justify-center">
        <div className="w-8 h-8 border-2 border-amber-400 border-t-transparent rounded-full animate-spin" />
      </div>
    )
  }

  const name = session.backendUser?.display_name ?? session.user?.name ?? "there"

  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 flex items-center justify-center px-4 py-16">
      <div className="w-full max-w-lg text-center">
        <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-amber-400/10 border border-amber-400/20 mb-6">
          <Sparkles className="w-8 h-8 text-amber-400" />
        </div>

        <h1 className="text-3xl font-bold text-white mb-3">
          Welcome, {name}!
        </h1>
        <p className="text-slate-400 leading-relaxed mb-10">
          Your Smart Resume account is ready. Let&apos;s set things up so you get
          the most out of every job application.
        </p>

        {/* Action cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-10">
          <Link
            href="/profile"
            className="group flex flex-col items-start gap-3 bg-slate-800/80 border border-slate-700 rounded-xl p-5 hover:border-amber-400/40 transition-colors text-left"
          >
            <div className="w-10 h-10 rounded-lg bg-violet-500/10 border border-violet-500/20 flex items-center justify-center">
              <Settings className="w-5 h-5 text-violet-400" />
            </div>
            <div>
              <h2 className="font-semibold text-slate-100 text-sm mb-0.5">Set up your profile</h2>
              <p className="text-xs text-slate-400">
                Add your contact info, career stage, and preferences.
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-colors ml-auto" />
          </Link>

          <Link
            href="/session/new"
            className="group flex flex-col items-start gap-3 bg-slate-800/80 border border-slate-700 rounded-xl p-5 hover:border-amber-400/40 transition-colors text-left"
          >
            <div className="w-10 h-10 rounded-lg bg-amber-500/10 border border-amber-500/20 flex items-center justify-center">
              <FileText className="w-5 h-5 text-amber-400" />
            </div>
            <div>
              <h2 className="font-semibold text-slate-100 text-sm mb-0.5">Tailor your first resume</h2>
              <p className="text-xs text-slate-400">
                Upload your resume and paste a job description to get started.
              </p>
            </div>
            <ArrowRight className="w-4 h-4 text-slate-500 group-hover:text-amber-400 transition-colors ml-auto" />
          </Link>
        </div>

        <Link
          href="/dashboard"
          className="text-sm text-slate-400 hover:text-slate-200 transition-colors underline underline-offset-4"
        >
          Go to dashboard →
        </Link>
      </div>
    </main>
  )
}
