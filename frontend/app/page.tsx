import Link from "next/link";
import { ArrowRight, FileText, Search, Sparkles, Download } from "lucide-react";

export default function LandingPage() {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-950 via-slate-900 to-slate-800 text-white">
      {/* Hero */}
      <section className="max-w-4xl mx-auto px-6 pt-24 pb-20 text-center">
        <div className="inline-flex items-center gap-2 bg-slate-800 border border-slate-700 rounded-full px-4 py-1.5 text-sm text-slate-300 mb-8">
          <Sparkles className="w-4 h-4 text-amber-400" />
          ATS-optimized · JD-specific · Never generic
        </div>
        <h1 className="text-5xl font-bold tracking-tight mb-6 leading-tight">
          Tailor your resume to{" "}
          <span className="text-amber-400">every job description</span>
          <br />in minutes.
        </h1>
        <p className="text-xl text-slate-400 mb-10 max-w-2xl mx-auto">
          Smart Resume Agent extracts every keyword recruiters look for, audits your resume
          against quality rules, rewrites it with exact JD phrasing, and exports a
          download-ready PDF — all without fabricating a word.
        </p>
        <Link
          href="/session/new?step=resume"
          className="inline-flex items-center gap-2 bg-amber-400 text-slate-900 font-semibold px-8 py-3.5 rounded-lg hover:bg-amber-300 transition-colors text-lg"
        >
          Get started free
          <ArrowRight className="w-5 h-5" />
        </Link>
        <p className="mt-4 text-slate-500 text-sm">No account required · Sessions expire after 24h</p>
      </section>

      {/* How it works */}
      <section className="max-w-4xl mx-auto px-6 pb-24">
        <h2 className="text-center text-2xl font-semibold mb-12 text-slate-200">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-4 gap-6">
          {[
            {
              icon: <FileText className="w-6 h-6 text-amber-400" />,
              step: "1",
              title: "Upload your resume",
              desc: "PDF, DOCX, or plain text. Fill in your info and paste the job description.",
            },
            {
              icon: <Search className="w-6 h-6 text-amber-400" />,
              step: "2",
              title: "Keyword extraction",
              desc: "The agent surfaces every must-have and nice-to-have ATS keyword from the JD.",
            },
            {
              icon: <Sparkles className="w-6 h-6 text-amber-400" />,
              step: "3",
              title: "AI rewrite",
              desc: "Your resume is rewritten with exact JD phrasing, strong action verbs, and quantified bullets.",
            },
            {
              icon: <Download className="w-6 h-6 text-amber-400" />,
              step: "4",
              title: "Download & apply",
              desc: "QA checklist confirms readiness. Export PDF or DOCX and submit with confidence.",
            },
          ].map((item) => (
            <div key={item.step} className="bg-slate-800 border border-slate-700 rounded-xl p-5">
              <div className="flex items-center gap-3 mb-3">
                <span className="w-7 h-7 rounded-full bg-slate-700 flex items-center justify-center text-xs font-bold text-slate-300">
                  {item.step}
                </span>
                {item.icon}
              </div>
              <h3 className="font-semibold text-slate-100 mb-1">{item.title}</h3>
              <p className="text-slate-400 text-sm">{item.desc}</p>
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
