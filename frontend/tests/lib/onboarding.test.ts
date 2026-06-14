import { describe, expect, it } from "vitest"
import {
  mustCompleteOnboarding,
  parseOnboardingStepParam,
  postAuthLandingPath,
  resolveOnboardingStepIndex,
} from "@/lib/auth/onboarding"
import type { BackendUser } from "@/auth"

const baseUser: BackendUser = {
  id: "u1",
  email: "a@b.com",
  display_name: "Test",
  tier: "free",
  credit_balance: 6,
  auth_provider: "email",
  email_verified_at: null,
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
  onboarding_completed_at: null,
  onboarding_ai_choice: null,
}

describe("mustCompleteOnboarding", () => {
  it("treats missing backendUser as incomplete", () => {
    expect(mustCompleteOnboarding({})).toBe(true)
    expect(mustCompleteOnboarding(null)).toBe(false)
  })

  it("honors onboarding_completed_at on the profile", () => {
    expect(mustCompleteOnboarding({ backendUser: baseUser })).toBe(true)
    expect(
      mustCompleteOnboarding({
        backendUser: { ...baseUser, onboarding_completed_at: "2026-01-01T00:00:00Z" },
      }),
    ).toBe(false)
  })
})

describe("postAuthLandingPath", () => {
  it("sends incomplete users to onboarding", () => {
    expect(postAuthLandingPath({ backendUser: baseUser })).toBe("/onboarding")
    expect(postAuthLandingPath({})).toBe("/onboarding")
  })

  it("sends completed users to dashboard", () => {
    expect(
      postAuthLandingPath({
        backendUser: { ...baseUser, onboarding_completed_at: "2026-01-01T00:00:00Z" },
      }),
    ).toBe("/dashboard")
  })
})

describe("parseOnboardingStepParam", () => {
  it("parses 1-based step query values", () => {
    expect(parseOnboardingStepParam("4")).toBe(3)
    expect(parseOnboardingStepParam("1")).toBe(0)
  })

  it("rejects invalid values", () => {
    expect(parseOnboardingStepParam(null)).toBeNull()
    expect(parseOnboardingStepParam("0")).toBeNull()
    expect(parseOnboardingStepParam("9")).toBeNull()
  })
})

describe("resolveOnboardingStepIndex", () => {
  it("starts at welcome when nothing is saved", () => {
    expect(resolveOnboardingStepIndex(baseUser)).toBe(0)
  })

  it("jumps to master resume after ai choice", () => {
    expect(
      resolveOnboardingStepIndex({
        ...baseUser,
        onboarding_ai_choice: "platform",
      }),
    ).toBe(2)
  })

  it("honors step=4 after master resume exists", () => {
    expect(
      resolveOnboardingStepIndex(
        { ...baseUser, onboarding_ai_choice: "platform" },
        { urlStepIndex: 3, hasMasterResume: true },
      ),
    ).toBe(3)
  })

  it("does not skip ahead without prerequisites", () => {
    expect(
      resolveOnboardingStepIndex(baseUser, { urlStepIndex: 3, hasMasterResume: false }),
    ).toBe(0)
  })
})
