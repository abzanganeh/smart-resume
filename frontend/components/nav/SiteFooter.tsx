import Link from "next/link";
import {
  COMPANY_LINE,
  COMPANY_NAME,
  COMPANY_URL,
  PRIVACY_EMAIL,
  PRODUCT_NAME,
} from "@/lib/brand";

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

const FOOTER_META =
  "text-xs leading-relaxed text-slate-500 dark:text-slate-500";

export function SiteFooter() {
  const copyrightYear = new Date().getFullYear();

  return (
    <footer
      role="contentinfo"
      className="mt-20 border-t border-slate-200 bg-slate-50/80 dark:border-slate-800 dark:bg-slate-950/80"
    >
      <div className="mx-auto max-w-5xl px-6 py-12 text-center">
        <nav aria-label="Legal" className="mb-8">
          <ul className="flex flex-col items-center gap-3 text-sm sm:flex-row sm:flex-wrap sm:justify-center sm:gap-x-8 sm:gap-y-3">
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

        <div className="space-y-1">
          <p className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100">
            {PRODUCT_NAME}
          </p>
          <p className={FOOTER_META}>
            <a
              href={COMPANY_URL}
              target="_blank"
              rel="noreferrer noopener"
              className={FOOTER_LINK}
            >
              {COMPANY_LINE}
            </a>
          </p>
          <p className={FOOTER_META}>
            <a href={`mailto:${PRIVACY_EMAIL}`} className={FOOTER_LINK}>
              {PRIVACY_EMAIL}
            </a>
          </p>
        </div>

        <div className="mt-8 space-y-2 border-t border-slate-200 pt-8 dark:border-slate-800">
          <p className={FOOTER_META}>
            © {copyrightYear} {COMPANY_NAME}
          </p>
          <p className={FOOTER_META}>
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
