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
      className="border-t border-slate-800 bg-slate-950/80 mt-20"
    >
      <div className="max-w-6xl mx-auto px-4 py-8 flex flex-col gap-4 text-sm text-slate-400 sm:flex-row sm:items-center sm:justify-between">
        <nav aria-label="Legal" className="flex flex-wrap gap-x-5 gap-y-2">
          {FOOTER_LINKS.map((link) => (
            <Link
              key={link.href}
              href={link.href}
              className="hover:text-amber-400 underline-offset-4 hover:underline"
            >
              {link.label}
            </Link>
          ))}
          <a
            href="mailto:privacy@zanganehai.com"
            className="hover:text-amber-400 underline-offset-4 hover:underline"
          >
            privacy@zanganehai.com
          </a>
        </nav>
        <p className="text-xs text-slate-500">
          © 2026 Hamed Zangane — Licensed under{" "}
          <a
            href="https://mariadb.com/bsl11/"
            target="_blank"
            rel="noreferrer noopener"
            className="hover:text-amber-400 underline-offset-4 hover:underline"
          >
            BSL 1.1
          </a>
        </p>
      </div>
    </footer>
  )
}
