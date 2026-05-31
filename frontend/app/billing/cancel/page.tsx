"use client"

import Link from "next/link"
import { XCircle } from "lucide-react"

export default function BillingCancelPage() {
  return (
    <main className="max-w-lg mx-auto px-4 py-20 text-center space-y-6">
      <div className="flex justify-center">
        <div className="w-16 h-16 rounded-full bg-slate-800 flex items-center justify-center">
          <XCircle className="w-8 h-8 text-slate-400" />
        </div>
      </div>

      <div className="space-y-2">
        <h1 className="text-2xl font-bold text-white">Not ready yet?</h1>
        <p className="text-slate-400">
          No worries — your checkout was cancelled and nothing was charged. Come back
          whenever you&apos;re ready to unlock full access.
        </p>
      </div>

      <div className="flex flex-col sm:flex-row gap-3 justify-center pt-2">
        <Link
          href="/billing"
          className="bg-amber-400 text-slate-900 font-semibold text-sm px-6 py-2.5 rounded-xl hover:bg-amber-300 transition-colors"
        >
          View plans
        </Link>
        <Link
          href="/"
          className="bg-slate-800 text-slate-200 font-medium text-sm px-6 py-2.5 rounded-xl hover:bg-slate-700 transition-colors border border-slate-700"
        >
          Back to home
        </Link>
      </div>
    </main>
  )
}
