import type { ReactNode } from "react"

/**
 * Shared shell for /legal/* pages.
 *
 * The legal copy is delivered as static React JSX (Next.js 16 server
 * component) instead of MDX so the build doesn't need an extra MDX
 * pipeline; updates flow through git history which doubles as the
 * required §19.9 "30-day notice" change log.
 */
export function LegalPageShell({
  title,
  lastUpdated,
  children,
}: {
  title: string
  lastUpdated: string
  children: ReactNode
}) {
  return (
    <main className="min-h-screen bg-gradient-to-br from-slate-100 via-white to-slate-200 dark:from-slate-950 dark:via-slate-900 dark:to-slate-800 px-4 py-12">
      <article className="mx-auto w-full max-w-3xl rounded-2xl border border-slate-200 dark:border-slate-800 bg-white/70 dark:bg-slate-900/70 p-8 shadow-2xl">
        <header className="mb-8 border-b border-slate-200 dark:border-slate-800 pb-6">
          <p className="text-xs uppercase tracking-widest text-slate-600 dark:text-slate-400">
            TalioCV — Legal
          </p>
          <h1 className="mt-1 text-3xl font-semibold text-slate-900 dark:text-white">{title}</h1>
          <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
            Last updated: <time dateTime={lastUpdated}>{lastUpdated}</time>
          </p>
        </header>
        <div className="prose dark:prose-invert max-w-none text-slate-700 dark:text-slate-300 [&_a]:text-amber-700 [&_a]:underline [&_a]:underline-offset-2 dark:[&_a]:text-amber-400 [&_h2]:mt-8 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-slate-900 dark:[&_h2]:text-white [&_h3]:mt-6 [&_h3]:text-lg [&_h3]:font-semibold [&_h3]:text-slate-900 dark:[&_h3]:text-white [&_li]:my-1 [&_p]:my-3 [&_ul]:list-disc [&_ul]:pl-6">
          {children}
        </div>
      </article>
    </main>
  )
}
