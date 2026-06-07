"use client"

import { SessionProvider as NextAuthSessionProvider } from "next-auth/react"
import { BackendTokenRefresh } from "@/components/nav/BackendTokenRefresh"

export function SessionProvider({ children }: { children: React.ReactNode }) {
  return (
    <NextAuthSessionProvider>
      <BackendTokenRefresh />
      {children}
    </NextAuthSessionProvider>
  )
}
