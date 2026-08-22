import Link from "next/link";
import { COMPANY_LINE, COMPANY_URL, PRODUCT_NAME } from "@/lib/brand";

const LEGAL_LINKS: {
  href: string;
  label: string;
  title?: string;
}[] = [
  { href: "/legal/terms", label: "Terms" },
  { href: "/legal/privacy", label: "Privacy Policy" },
  { href: "/legal/sub-processors", label: "Sub-processors" },
  {
    href: "/legal/ccpa",
    label: "CCPA",
    title: "Do Not Sell My Personal Information",
  },
  { href: "/legal/contact", label: "DPO Contact" },
];

const FOOTER_LINK =
  "text-slate-600 underline-offset-4 transition-colors hover:text-amber-800 hover:underline dark:text-slate-400 dark:hover:text-amber-400";

export function SiteFooter() {
  return (
    <footer
      role="contentinfo"
      className="mt-20 border-t border-slate-200 bg-slate-50/80 dark:border-slate-800 dark:bg-slate-950/80"
    >
      <div className="mx-auto max-w-5xl px-6 py-10">
        <div className="grid gap-8 md:grid-cols-[minmax(0,11rem)_1fr] md:gap-12 lg:grid-cols-[minmax(0,13rem)_1fr]">
          <div className="space-y-1">
            <p className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
              {PRODUCT_NAME}
            </p>
            <p className="text-xs text-slate-500 dark:text-slate-500">
              <a
                href={COMPANY_URL}
                target="_blank"
                rel="noreferrer noopener"
                className={FOOTER_LINK}
              >
                {COMPANY_LINE}
              </a>
            </p>
          </div>

          <div className="space-y-5">
            <nav aria-label="Legal">
              <ul className="grid grid-cols-2 gap-x-6 gap-y-2.5 text-sm sm:grid-cols-3 lg:grid-cols-5">
                {LEGAL_LINKS.map((link) => (
                  <li key={link.href}>
                    <Link
                      href={link.href}
                      className={FOOTER_LINK}
                      title={link.title}
                    >
                      {link.label}
                    </Link>
                  </li>
                ))}
              </ul>
            </nav>

            <p className="text-sm text-slate-600 dark:text-slate-400">
              <span className="text-slate-500 dark:text-slate-500">Privacy </span>
              <a href="mailto:privacy@zanganehai.com" className={FOOTER_LINK}>
                privacy@zanganehai.com
              </a>
            </p>
          </div>
        </div>

        <div className="mt-8 flex flex-col gap-2 border-t border-slate-200 pt-6 text-xs text-slate-500 dark:border-slate-800 dark:text-slate-500 sm:flex-row sm:flex-wrap sm:items-center sm:justify-between sm:gap-x-4">
          <p>© 2026 Alireza Barzin Zanganeh</p>
          <p>
            Licensed under{" "}
            <a
              href="https://mariadb.com/bsl11/"
              target="_blank"
              rel="noreferrer noopener"
              className={FOOTER_LINK}
            >
              BSL 1.1
            </a>
          </p>
        </div>
      </div>
    </footer>
  );
}
