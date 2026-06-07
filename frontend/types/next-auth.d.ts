import "next-auth"
import "next-auth/jwt"
import type { BackendUser } from "@/auth"

declare module "next-auth" {
  interface Session {
    backendAccessToken?: string
    backendExpiresAt?: number
    backendUser?: BackendUser
    error?: string
  }
  interface User {
    backendAccessToken?: string
    backendExpiresAt?: number
    backendUser?: BackendUser
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    backendAccessToken?: string
    backendExpiresAt?: number
    backendUser?: BackendUser
    error?: string
  }
}
