import Link from "next/link";
import { ArrowRight, Download, FileText, Key, Search, Sparkles, Zap } from "lucide-react";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white">

      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-24 pb-16 text-center">
        <div className="inline-flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-300 mb-8">
          <Sparkles className="w-4 h-4 text-amber-400" />
          ATS-optimized · JD-specific · Your API key, your cost
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-6 leading-tight">
          Tailor your resume to{" "}
          <span className="text-amber-400">every job description</span>
          <br />in minutes.
        </h1>
        <p className="text-xl text-slate-400 mb-4 max-w-2xl mx-auto">
          Smart Resume Agent extracts every ATS keyword, audits your resume, rewrites it with
          exact JD phrasing, and exports a download-ready PDF — all without fabricating a word.
        </p>
        <p className="text-sm text-slate-500 mb-10 max-w-xl mx-auto">
          Powered by <strong className="text-slate-300">your own AI API key</strong> — we never store it,
          never charge you for AI calls. Gemini and Ollama have free tiers.
        </p>
        <Link
          href="/auth"
          className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg"
        >
          Get started free
          <ArrowRight className="w-5 h-5" />
        </Link>
        <p className="mt-4 text-slate-500 text-sm">Free account · 6 credits included · No credit card required</p>
      </section>

      {/* Provider badges */}
      <section className="max-w-3xl mx-auto px-6 pb-16">
        <p className="text-center text-slate-500 text-xs uppercase tracking-widest mb-6">Works with</p>
        <div className="flex flex-wrap justify-center gap-3">
          {[
            { name: "Google Gemini", emoji: "✨", badge: "Free tier", badgeColor: "bg-emerald-900/50 text-emerald-300 border-emerald-700" },
            { name: "OpenRouter", emoji: "🔀", badge: "Free models", badgeColor: "bg-emerald-900/50 text-emerald-300 border-emerald-700" },
            { name: "Ollama", emoji: "🦙", badge: "100% free", badgeColor: "bg-emerald-900/50 text-emerald-300 border-emerald-700" },
            { name: "OpenAI", emoji: "⚡", badge: "Pay-as-you-go", badgeColor: "bg-slate-800 text-slate-400 border-slate-700" },
            { name: "Anthropic", emoji: "🧠", badge: "Pay-as-you-go", badgeColor: "bg-slate-800 text-slate-400 border-slate-700" },
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

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <h2 className="text-center text-2xl font-semibold mb-3 text-slate-200">How it works</h2>
        <p className="text-center text-slate-500 text-sm mb-12">Five steps, entirely in your browser.</p>
        <div className="grid grid-cols-1 md:grid-cols-5 gap-4">
          {[
            {
              icon: <Key className="w-5 h-5 text-violet-400" />,
              step: "1",
              title: "Choose your AI",
              desc: "Pick a provider and paste your API key. We guide you step-by-step. Key stays in your browser only.",
              highlight: true,
            },
            {
              icon: <FileText className="w-5 h-5 text-amber-400" />,
              step: "2",
              title: "Upload resume",
              desc: "PDF, DOCX, or plain text. Max 5 MB.",
              highlight: false,
            },
            {
              icon: <Search className="w-5 h-5 text-amber-400" />,
              step: "3",
              title: "Paste job description",
              desc: "The agent extracts every must-have ATS keyword.",
              highlight: false,
            },
            {
              icon: <Sparkles className="w-5 h-5 text-amber-400" />,
              step: "4",
              title: "AI rewrite",
              desc: "Rewritten with exact JD phrasing. Never fabricates metrics.",
              highlight: false,
            },
            {
              icon: <Download className="w-5 h-5 text-amber-400" />,
              step: "5",
              title: "Download",
              desc: "QA checklist, then export PDF or DOCX.",
              highlight: false,
            },
          ].map((item) => (
            <div
              key={item.step}
              className={`rounded-xl p-5 border ${
                item.highlight
                  ? "bg-violet-950/40 border-violet-700/60 ring-1 ring-violet-600/30"
                  : "bg-slate-800 border-slate-700"
              }`}
            >
              <div className="flex items-center gap-2 mb-3">
                <span className={`w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold ${
                  item.highlight ? "bg-violet-700 text-white" : "bg-slate-700 text-slate-300"
                }`}>
                  {item.step}
                </span>
                {item.icon}
              </div>
              <h3 className="font-semibold text-slate-100 mb-1 text-sm">{item.title}</h3>
              <p className="text-slate-400 text-xs leading-relaxed">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Cost callout */}
      <section className="max-w-3xl mx-auto px-6 pb-24">
        <div className="bg-slate-800/60 border border-slate-700 rounded-2xl p-8 text-center">
          <Zap className="w-8 h-8 text-amber-400 mx-auto mb-4" />
          <h2 className="text-xl font-semibold mb-3">Zero cost to run this site</h2>
          <p className="text-slate-400 text-sm max-w-lg mx-auto mb-6">
            Your API key goes directly to the LLM provider. This app acts as a middleman for
            orchestration only — it <strong className="text-slate-200">never bills you</strong>, never stores
            your key, and disappears when the tab closes.
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
            {[
              {
                emoji: "✨",
                name: "Google Gemini",
                detail: "Free tier via AI Studio — 1,500 requests/day. No credit card needed.",
                recommended: true,
              },
              {
                emoji: "🦙",
                name: "Ollama (local)",
                detail: "Runs entirely on your machine. Completely free. Requires ~8 GB RAM.",
                recommended: false,
              },
              {
                emoji: "🔀",
                name: "OpenRouter",
                detail: "Free models available (Llama 3, Mistral). Pay-as-you-go for premium.",
                recommended: false,
              },
            ].map((p) => (
              <div key={p.name} className="bg-slate-900 rounded-xl p-4 border border-slate-700">
                <div className="flex items-center gap-2 mb-2">
                  <span className="text-xl">{p.emoji}</span>
                  <span className="font-semibold text-slate-100 text-sm">{p.name}</span>
                  {p.recommended && (
                    <span className="ml-auto text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 border border-emerald-700">
                      Recommended
                    </span>
                  )}
                </div>
                <p className="text-xs text-slate-400 leading-relaxed">{p.detail}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* CTA footer */}
      <section className="text-center pb-24">
        <Link
          href="/auth"
          className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg"
        >
          Start tailoring your resume
          <ArrowRight className="w-5 h-5" />
        </Link>
        <p className="mt-4 text-slate-500 text-sm">Takes about 2 minutes of setup. Free account, 6 credits included.</p>
      </section>

    </main>
  );
}
