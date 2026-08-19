import Link from "next/link"

const FOOTER_LINKS: { href: string; label: string }[] = [
  { href: "/legal/terms", label: "Terms" },
  { href: "/legal/privacy", label: "Privacy Policy" },
  { href: "/legal/sub-processors", label: "Sub-processors" },
  { href: "/legal/ccpa", label: "Do Not Sell My Personal Info" },
  { href: "/legal/contact", label: "DPO Contact" },
]

export function SiteFooter() {
  return (
    <footer
      role="contentinfo"
      className="border-t border-slate-200 dark:border-slate-800 bg-slate-50/80 dark:bg-slate-950/80 mt-20"
    >
      <div className="max-w-6xl mx-auto px-4 py-8 grid gap-3 text-sm text-slate-600 dark:text-slate-400 sm:grid-cols-[minmax(0,1fr)_auto] sm:items-center">
        <nav aria-label="Legal" className="flex flex-wrap items-center gap-x-5 gap-y-2">
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="hover:text-amber-800 dark:hover:text-amber-400 underline-offset-4 hover:underline"
            >
              {link.label}
            </Link>
          ))}
          <a
            href="mailto:privacy@zanganehai.com"
            className="hover:text-amber-800 dark:hover:text-amber-400 underline-offset-4 hover:underline"
          >
            privacy@zanganehai.com
          </a>
        </nav>
        <p className="text-xs text-slate-600 dark:text-slate-400 sm:text-right sm:whitespace-nowrap">
          © 2026 Alireza Barzin Zanganeh ·{" "}
          <a
            href="https://mariadb.com/bsl11/"
            target="_blank"
            rel="noreferrer noopener"
            className="hover:text-amber-800 dark:hover:text-amber-400 underline-offset-4 hover:underline"
          >
            BSL 1.1
          </a>
        </p>
      </div>
    </footer>
  )
}
