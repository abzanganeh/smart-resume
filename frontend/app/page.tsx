import Link from "next/link";
import { BrandLogo } from "@/components/brand/BrandLogo";
import { ProductScreenshot } from "@/components/brand/ProductScreenshot";
import {
  ArrowRight,
  BookOpen,
  Briefcase,
  CheckCircle,
  Download,
  FileText,
  Layers,
  MessageSquare,
  Mic,
  Search,
  Sparkles,
  Star,
  Zap,
} from "lucide-react";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white">

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-24 pb-16 text-center">
        <div className="flex justify-center mb-8">
          <BrandLogo className="h-16 w-auto max-w-[min(100%,320px)]" priority />
        </div>
        <div className="inline-flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-300 mb-8">
          <Sparkles className="w-4 h-4 text-amber-400" />
          ATS-optimized · Evidence-based · Never fabricates metrics
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-6 leading-tight">
          Your entire job search,{" "}
          <span className="text-amber-400">powered by AI.</span>
        </h1>
        <p className="text-xl text-slate-400 mb-4 max-w-2xl mx-auto">
          Build your master resume by speaking, tailor it to every job description in minutes, find
          matching jobs, write cover letters, and track every application — all in one place.
        </p>
        <p className="text-sm text-slate-500 mb-10 max-w-xl mx-auto">
          Create a free account in under a minute — 6 credits included, no credit card.
          Use our AI models or bring your own API key.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            href="/auth?mode=register"
            className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg"
          >
            Create free account
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            href="/auth"
            className="inline-flex items-center gap-2 border border-slate-700 text-slate-300 hover:border-slate-500 hover:text-white font-medium px-6 py-3.5 rounded-lg transition-colors text-base"
          >
            Sign in
          </Link>
        </div>
        <p className="mt-4 text-slate-500 text-sm">
          New here?{" "}
          <Link href="/auth?mode=register" className="text-amber-400 hover:text-amber-300 font-medium">
            Register free
          </Link>
          {" · "}
          6 credits on signup · No credit card required
        </p>
        <div className="mt-14 max-w-3xl mx-auto text-left">
          <ProductScreenshot priority />
        </div>
      </section>

      {/* How it works */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <h2 className="text-center text-2xl font-semibold mb-3 text-slate-200">How it works</h2>
        <p className="text-center text-slate-500 text-sm mb-12">From zero to tailored resume in under 15 minutes.</p>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-5">
          {[
            {
              step: "1",
              icon: <Mic className="w-5 h-5 text-indigo-400" />,
              title: "Build your master resume",
              desc: "Upload a file, speak your career story (we transcribe it), or let the AI interview you with structured career questions.",
              accent: "indigo",
            },
            {
              step: "2",
              icon: <Search className="w-5 h-5 text-amber-400" />,
              title: "Paste a job description",
              desc: "The agent extracts every must-have and nice-to-have ATS keyword from the JD.",
              accent: "amber",
            },
            {
              step: "3",
              icon: <Sparkles className="w-5 h-5 text-amber-400" />,
              title: "AI rewrites your resume",
              desc: "Four-phase pipeline: keyword audit → gap analysis → evidence-based rewrite → ATS quality check.",
              accent: "amber",
            },
            {
              step: "4",
              icon: <Download className="w-5 h-5 text-emerald-400" />,
              title: "Export & apply",
              desc: "Download a clean PDF or DOCX. Generate a matching cover letter. Track your application in one click.",
              accent: "emerald",
            },
          ].map((item) => (
            <div
              key={item.step}
              className="rounded-xl p-5 border bg-slate-800/60 border-slate-700 space-y-3"
            >
              <div className="flex items-center gap-2">
                <span className="w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold bg-slate-700 text-slate-300">
                  {item.step}
                </span>
                {item.icon}
              </div>
              <h3 className="font-semibold text-slate-100 text-sm">{item.title}</h3>
              <p className="text-slate-400 text-xs leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Feature grid */}
      <section className="max-w-5xl mx-auto px-6 pb-24">
        <h2 className="text-center text-2xl font-semibold mb-3 text-slate-200">Everything in one platform</h2>
        <p className="text-center text-slate-500 text-sm mb-12">
          Not just a resume rewriter — a full job-search co-pilot.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
          {[
            {
              icon: <Mic className="w-5 h-5 text-indigo-400" />,
              title: "Story Mode",
              desc: "Speak your career into the mic. Choose free recording with per-segment AI coaching, or a fully structured coached interview where the AI asks the questions.",
              badge: null,
            },
            {
              icon: <Layers className="w-5 h-5 text-amber-400" />,
              title: "Master Resume",
              desc: "A permanent semantic store of your experience. Every tailored resume draws from it — so rewrites use your real skills, not hallucinations.",
              badge: null,
            },
            {
              icon: <Sparkles className="w-5 h-5 text-amber-400" />,
              title: "ATS Optimization",
              desc: "Phase 1 extracts every keyword. Phase 4 scores your resume against the JD and gives you one-click quick-win suggestions to close gaps.",
              badge: null,
            },
            {
              icon: <MessageSquare className="w-5 h-5 text-violet-400" />,
              title: "AI Chat & Inline Editing",
              desc: 'Chat panel for freeform edits ("add a metric to the second bullet"), per-section regeneration, undo/redo version history.',
              badge: null,
            },
            {
              icon: <FileText className="w-5 h-5 text-sky-400" />,
              title: "Cover Letter Generator",
              desc: "One click generates a tailored cover letter from your master resume and the job description. Edit inline, export as PDF.",
              badge: null,
            },
            {
              icon: <Search className="w-5 h-5 text-emerald-400" />,
              title: "Job Search",
              desc: "Search matching jobs directly from the platform. Set preferences, block companies, and save listings to your tracker in one click.",
              badge: null,
            },
            {
              icon: <Briefcase className="w-5 h-5 text-orange-400" />,
              title: "Application Tracker",
              desc: "Kanban-style board tracks every application from Applied → Interview → Offer → Closed. Notes, attachments, and status history.",
              badge: null,
            },
            {
              icon: <Star className="w-5 h-5 text-pink-400" />,
              title: "Job Fit Score",
              desc: "Semantic similarity between your master resume and any job description — before you spend a credit tailoring.",
              badge: null,
            },
            {
              icon: <Zap className="w-5 h-5 text-amber-400" />,
              title: "BYOK Support",
              desc: "Bring your own OpenAI, Anthropic, Gemini, or OpenRouter key. Your key never leaves your browser session.",
              badge: null,
            },
          ].map((feature) => (
            <div
              key={feature.title}
              className="rounded-xl border border-slate-700 bg-slate-800/40 p-5 space-y-2"
            >
              <div className="flex items-center gap-2">
                {feature.icon}
                <h3 className="font-semibold text-slate-100 text-sm">{feature.title}</h3>
                {feature.badge && (
                  <span className="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700">
                    {feature.badge}
                  </span>
                )}
              </div>
              <p className="text-slate-400 text-xs leading-relaxed">{feature.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* AI providers */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <p className="text-center text-slate-500 text-xs uppercase tracking-widest mb-6">Supported AI providers</p>
        <div className="flex flex-wrap justify-center gap-3">
          {[
            { name: "Google Gemini", emoji: "✨", badge: "Platform default", badgeColor: "bg-indigo-900/50 text-indigo-300 border-indigo-700" },
            { name: "Claude (Anthropic)", emoji: "🧠", badge: "Best quality", badgeColor: "bg-purple-900/50 text-purple-300 border-purple-700" },
            { name: "OpenAI", emoji: "⚡", badge: "BYOK", badgeColor: "bg-slate-800 text-slate-400 border-slate-700" },
            { name: "OpenRouter", emoji: "🔀", badge: "BYOK · Free models", badgeColor: "bg-emerald-900/50 text-emerald-300 border-emerald-700" },
            { name: "Ollama", emoji: "🦙", badge: "BYOK · Local · Free", badgeColor: "bg-emerald-900/50 text-emerald-300 border-emerald-700" },
          ].map((p) => (
            <div key={p.name} className="flex items-center gap-2 bg-slate-800/80 border border-slate-700 rounded-lg px-4 py-2.5">
              <span className="text-lg">{p.emoji}</span>
              <span className="text-sm font-medium text-slate-200">{p.name}</span>
              <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${p.badgeColor}`}>
                {p.badge}
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* Quality guarantee */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <div className="bg-slate-800/60 border border-slate-700 rounded-2xl p-8">
          <h2 className="text-xl font-semibold mb-6 text-center">Built on quality rules, not guesswork</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              "Never fabricates metrics — only uses content from your master resume",
              "8-point QA checklist before every export",
              "ATS score with before/after delta so you see the improvement",
              "Every rewrite is evidence-sourced to your actual experience",
              "Inline editor + per-section AI regeneration — full control",
              "Undo / redo through complete version history",
            ].map((point) => (
              <div key={point} className="flex items-start gap-2.5">
                <CheckCircle className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                <p className="text-slate-300 text-sm leading-relaxed">{point}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA footer */}
      <section className="text-center pb-24 px-6">
        <h2 className="text-2xl font-semibold mb-3 text-slate-100">Ready to land your next role?</h2>
        <p className="text-slate-400 text-sm mb-8 max-w-md mx-auto">
          Create your free account and get 6 credits to tailor your first resume. No credit card, no commitment.
        </p>
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4">
          <Link
            href="/auth?mode=register"
            className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg"
          >
            Create free account
            <ArrowRight className="w-5 h-5" />
          </Link>
          <Link
            href="/auth"
            className="text-slate-400 hover:text-slate-200 text-sm font-medium transition-colors"
          >
            Already have an account? Sign in
          </Link>
        </div>
        <p className="mt-4 text-slate-500 text-sm">Takes about 2 minutes to register and get your first tailored resume.</p>
      </section>

    </main>
  );
}
