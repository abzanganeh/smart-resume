"use client"

import { SessionProvider as NextAuthSessionProvider } from "next-auth/react"
import { BackendTokenRefresh } from "@/components/nav/BackendTokenRefresh"
import { StaleSessionGuard } from "@/components/nav/StaleSessionGuard"

export function SessionProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextAuthSessionProvider refetchOnWindowFocus={false} refetchInterval={0}>
      <BackendTokenRefresh />
      <StaleSessionGuard />
      {children}
    </NextAuthSessionProvider>
  )
}
