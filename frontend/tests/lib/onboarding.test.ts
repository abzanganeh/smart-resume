import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  mustCompleteOnboarding,
  parseOnboardingStepParam,
  postAuthLandingPath,
  resolveOnboardingStepIndex,
} from "@/lib/auth/onboarding";
import type { BackendUser } from "@/auth";

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
};

describe("mustCompleteOnboarding", () => {
  it("treats missing backendUser as incomplete", () => {
    assert.equal(mustCompleteOnboarding({}), true);
    assert.equal(mustCompleteOnboarding(null), false);
  });

  it("honors onboarding_completed_at on the profile", () => {
    assert.equal(mustCompleteOnboarding({ backendUser: baseUser }), true);
    assert.equal(
      mustCompleteOnboarding({
        backendUser: { ...baseUser, onboarding_completed_at: "2026-01-01T00:00:00Z" },
      }),
      false,
    );
  });
});

describe("postAuthLandingPath", () => {
  it("sends incomplete users to onboarding", () => {
    assert.equal(postAuthLandingPath({ backendUser: baseUser }), "/onboarding");
    assert.equal(postAuthLandingPath({}), "/onboarding");
  });

  it("sends completed users to dashboard", () => {
    assert.equal(
      postAuthLandingPath({
        backendUser: { ...baseUser, onboarding_completed_at: "2026-01-01T00:00:00Z" },
      }),
      "/dashboard",
    );
  });
});

describe("parseOnboardingStepParam", () => {
  it("parses 1-based step query values", () => {
    assert.equal(parseOnboardingStepParam("4"), 3);
    assert.equal(parseOnboardingStepParam("1"), 0);
  });

  it("rejects invalid values", () => {
    assert.equal(parseOnboardingStepParam(null), null);
    assert.equal(parseOnboardingStepParam("0"), null);
    assert.equal(parseOnboardingStepParam("9"), null);
  });
});

describe("resolveOnboardingStepIndex", () => {
  it("starts at welcome when nothing is saved", () => {
    assert.equal(resolveOnboardingStepIndex(baseUser), 0);
  });

  it("jumps to master resume after ai choice", () => {
    assert.equal(
      resolveOnboardingStepIndex({
        ...baseUser,
        onboarding_ai_choice: "platform",
      }),
      2,
    );
  });

  it("honors step=4 after master resume exists", () => {
    assert.equal(
      resolveOnboardingStepIndex(
        { ...baseUser, onboarding_ai_choice: "platform" },
        { urlStepIndex: 3, hasMasterResume: true },
      ),
      3,
    );
  });

  it("does not skip ahead without prerequisites", () => {
    assert.equal(
      resolveOnboardingStepIndex(baseUser, { urlStepIndex: 3, hasMasterResume: false }),
      0,
    );
  });
});
