"use client"

import { DashboardView } from "@/components/dashboard/DashboardView"
import { useRequireAuth } from "@/lib/auth/guards"
import { Loader2 } from "lucide-react"

export default function DashboardPage() {
  const { session, status } = useRequireAuth("/dashboard")

  if (status === "loading" || !session?.backendAccessToken) {
    return (
      <div className="min-h-[60vh] flex items-center justify-center">
        <Loader2 className="w-8 h-8 animate-spin text-amber-400" />
      </div>
    )
  }

  return <DashboardView token={session.backendAccessToken} />
}
