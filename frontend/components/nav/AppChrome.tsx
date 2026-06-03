"use client"

import { usePathname } from "next/navigation"
import { NavBar } from "@/components/nav/NavBar"
import { SiteFooter } from "@/components/nav/SiteFooter"

/** Hides the public site chrome on /admin/* (separate admin auth + layout). */
export function AppChrome({ children }: { children: React.ReactNode }) {
  const pathname = usePathname()
  const isAdminRoute = pathname?.startsWith("/admin") ?? false

  return (
    <>
      {!isAdminRoute && <NavBar />}
      <div className="flex-1">{children}</div>
      {!isAdminRoute && <SiteFooter />}
    </>
  )
}
