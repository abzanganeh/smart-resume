"use client"

import { usePathname } from "next/navigation"
import { NavBar } from "@/components/nav/NavBar"
import { SiteFooter } from "@/components/nav/SiteFooter"
import { OfferPopupHost } from "@/components/billing/OfferPopupHost"

/** Hides chrome on /admin/* and /auth (auth has its own centered brand). */
export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isAdminRoute = pathname?.startsWith("/admin") ?? false
  const isAuthRoute =
    pathname === "/auth" || Boolean(pathname?.startsWith("/auth/"))

  const showPublicChrome = !isAdminRoute && !isAuthRoute

  return (
    <>
      {showPublicChrome && <NavBar />}
      <div className="flex-1">{children}</div>
      {showPublicChrome && <SiteFooter />}
      {showPublicChrome && <OfferPopupHost />}
    </>
  )
}
