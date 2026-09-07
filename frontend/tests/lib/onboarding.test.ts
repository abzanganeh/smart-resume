import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  isOnboardingExempt,
  mustCompleteOnboarding,
  onboardingStepAfterMasterUpload,
  ONBOARDING_JOB_TITLES_STEP_INDEX,
  ONBOARDING_MASTER_STEP_INDEX,
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
  credit_balance: 3,
  auth_provider: "email",
  email_verified_at: null,
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
  onboarding_completed_at: null,
  onboarding_ai_choice: null,
};

describe("isOnboardingExempt", () => {
  it("lets password reset complete before onboarding", () => {
    assert.equal(isOnboardingExempt("/auth/reset"), true);
    assert.equal(isOnboardingExempt("/auth"), false);
    assert.equal(isOnboardingExempt("/dashboard"), false);
  });

  it("lets email verification and settings complete before onboarding", () => {
    assert.equal(isOnboardingExempt("/auth/verify"), true);
    assert.equal(isOnboardingExempt("/settings"), true);
    assert.equal(isOnboardingExempt("/settings/billing"), true);
  });

  it("does not over-match auth or settings prefixes", () => {
    assert.equal(isOnboardingExempt("/auth"), false);
    assert.equal(isOnboardingExempt("/settingsfoo"), false);
    assert.equal(isOnboardingExempt("/dashboard"), false);
  });
});

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
    assert.equal(parseOnboardingStepParam("5"), 4);
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

  it("honors step=4 after ai choice (job titles intro)", () => {
    assert.equal(
      resolveOnboardingStepIndex(
        { ...baseUser, onboarding_ai_choice: "platform" },
        { urlStepIndex: 3 },
      ),
      3,
    );
  });

  it("lands on done step via url after ai choice", () => {
    assert.equal(
      resolveOnboardingStepIndex(
        { ...baseUser, onboarding_ai_choice: "platform" },
        { urlStepIndex: 4 },
      ),
      4,
    );
  });

  it("does not skip ahead without ai choice", () => {
    assert.equal(
      resolveOnboardingStepIndex(baseUser, { urlStepIndex: 3 }),
      0,
    );
  });
});

describe("onboardingStepAfterMasterUpload", () => {
  it("advances from master step to job titles", () => {
    assert.equal(
      onboardingStepAfterMasterUpload(ONBOARDING_MASTER_STEP_INDEX),
      ONBOARDING_JOB_TITLES_STEP_INDEX,
    );
  });

  it("leaves other steps unchanged", () => {
    assert.equal(onboardingStepAfterMasterUpload(0), 0);
    assert.equal(onboardingStepAfterMasterUpload(4), 4);
  });
});
