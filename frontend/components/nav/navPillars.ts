/** Top navigation pillar definitions (desktop dropdowns + mobile flatten). */

export type NavLinkDef = { href: string; label: string }

export type NavPillar = {
  id: string
  label: string
  links: readonly NavLinkDef[]
  comingSoon?: boolean
}

export const NAV_PILLARS: readonly NavPillar[] = [
  {
    id: "home",
    label: "Dashboard",
    links: [{ href: "/dashboard", label: "Dashboard" }],
  },
  {
    id: "resume",
    label: "Resume",
    links: [
      { href: "/profile", label: "Master resume" },
      { href: "/session/new", label: "Tailor for a job" },
      { href: "/cover-letter/new", label: "Cover letter" },
      { href: "/fit", label: "Job fit" },
    ],
  },
  {
    id: "jobs",
    label: "Jobs",
    links: [
      { href: "/jobs/setup", label: "Job roles" },
      { href: "/jobs", label: "Search jobs" },
      { href: "/tracker", label: "Applications" },
      { href: "/career-watch", label: "Career Watch" },
    ],
  },
  {
    id: "prepare",
    label: "Prepare",
    comingSoon: true,
    links: [{ href: "#", label: "Interview prep (coming soon)" }],
  },
] as const

/** Flat list for mobile scroll bar — excludes /dashboard (fixed pill in header). */
export const MOBILE_NAV_LINKS: readonly NavLinkDef[] = NAV_PILLARS.flatMap((pillar) =>
  pillar.comingSoon ? [] : pillar.links,
).filter((link) => link.href !== "/dashboard")

/** Public landing header — shown to signed-out visitors only. */
export const LANDING_NAV_LINKS: readonly NavLinkDef[] = [
  { href: "/#pricing", label: "Pricing" },
  { href: "/#faq", label: "FAQ" },
  { href: "/checkup", label: "CV Checkup" },
] as const

export function landingNavHrefFromLocation(
  pathname: string,
  hash: string = "",
): string | null {
  const match = LANDING_NAV_LINKS.find((link) =>
    landingNavLinkIsActive(pathname, link.href, hash),
  )
  return match?.href ?? null
}

export function landingNavLinkIsActive(
  pathname: string,
  href: string,
  hash: string = "",
): boolean {
  if (href === "/checkup") {
    return pathname === "/checkup" || pathname.startsWith("/checkup/")
  }
  if (href.startsWith("/#")) {
    if (pathname !== "/") return false
    return hash === href.slice(1)
  }
  return navPathIsActive(pathname, href)
}

export function navPathIsActive(pathname: string, href: string): boolean {
  if (href === "#") return false
  if (href === "/dashboard") return pathname === "/dashboard"
  if (href === "/jobs/setup") return pathname.startsWith("/jobs/setup")
  return pathname === href || pathname.startsWith(`${href}/`)
}

export function navPillarIsActive(pathname: string, pillar: NavPillar): boolean {
  return pillar.links.some((link) => navPathIsActive(pathname, link.href))
}
