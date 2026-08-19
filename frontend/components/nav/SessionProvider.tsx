"use client"

import type { Session } from "next-auth"
import { SessionProvider as NextAuthSessionProvider } from "next-auth/react"
import { BackendTokenRefresh } from "@/components/nav/BackendTokenRefresh"
import { StaleSessionGuard } from "@/components/nav/StaleSessionGuard"

export function SessionProvider({
  children,
  session,
}: {
  children: React.ReactNode
  session?: Session | null
}) {
  return (
    <NextAuthSessionProvider
      session={session}
      refetchOnWindowFocus={false}
      refetchInterval={0}
    >
      <BackendTokenRefresh />
      <StaleSessionGuard />
      {children}
    </NextAuthSessionProvider>
  )
}
