"use client"

import { Suspense } from "react"
import Link from "next/link"
import { ArrowLeft, Search } from "lucide-react"
import { useRouter, useSearchParams } from "next/navigation"
import { useRequireAuth } from "@/lib/auth/guards"
import { JobTitlePicker } from "@/components/jobs/JobTitlePicker"

/** Exported for unit tests. Reject anything that isn't a same-origin path. */
export function safeReturnPath(raw: string | null): string {
  const value = (raw ?? "").trim()
  if (
    !value.startsWith("/") ||
    value.startsWith("//") ||
    value.startsWith("/\\")
  ) {
    return "/jobs"
  }
  return value
}

function SetupContent() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const returnTo = safeReturnPath(searchParams.get("return"))
  const { session, status } = useRequireAuth("/jobs/setup")
  const token = session?.backendAccessToken ?? ""

  if (status === "loading" || !session) {
    return (
      <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center text-slate-600 dark:text-slate-400">
        Loading…
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-white">
      <div className="max-w-2xl mx-auto px-6 py-12">
        <Link
          href="/dashboard"
          className="inline-flex items-center gap-2 text-sm text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200 mb-8 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          Back to Dashboard
        </Link>

        <div className="text-center mb-8">
          <h1 className="text-2xl font-bold flex items-center justify-center gap-2">
            <Search className="w-7 h-7 text-amber-700 dark:text-amber-400" />
            Choose roles to search for
          </h1>
          <p className="text-slate-600 dark:text-slate-400 text-sm mt-2">
            TalioCV matches your story to real openings from our company job corpus.
          </p>
        </div>

        <div className="rounded-xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-6">
          <JobTitlePicker
            accessToken={token}
            submitLabel="Save and search jobs"
            onComplete={async () => {
              router.push(returnTo)
            }}
          />
        </div>
      </div>
    </div>
  )
}

export default function JobSearchSetupPage() {
  return (
    <Suspense
      fallback={
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 flex items-center justify-center">
          Loading…
        </div>
      }
    >
      <SetupContent />
    </Suspense>
  )
}
