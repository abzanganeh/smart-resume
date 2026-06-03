"use client"

import { useEffect } from "react"
import { signOut } from "next-auth/react"
import { DashboardView } from "@/components/dashboard/DashboardView"
import { useRequireAuth } from "@/lib/auth/guards"
import { Loader2 } from "lucide-react"

export default function DashboardPage() {
  const { session, status } = useRequireAuth("/dashboard")

  // No backend token — sign out of NextAuth so /auth works cleanly
  const noToken = status !== "loading" && session !== null && session !== undefined && !session.backendAccessToken
  useEffect(() => {
    if (noToken) {
      signOut({ callbackUrl: "/auth?callbackUrl=%2Fdashboard" })
    }
  }, [noToken])

  if (status === "loading" || noToken) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  if (!session?.backendAccessToken) return null

  return <DashboardView token={session.backendAccessToken} />
}
