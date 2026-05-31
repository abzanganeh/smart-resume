/**
 * Component tests for <LLMTierSelector />.
 *
 * Mirrors the pattern of UsageWidget.test.tsx: framework-agnostic
 * assertions against the pure helpers (`deriveTierVisualState` and
 * `purchaseOptionsForTier`) that drive the visual state of the
 * selector.  These cover the three personas required by P12 §20:
 *
 *   1. free user    → all upgrade tiers are locked (un-runnable)
 *   2. better-credit user → Better is runnable + shows credits badge
 *   3. best-subscribed user → Best is runnable; Yearly add-on visible
 *      only if base subscription cycle is yearly
 *
 * Plus the soft-cap fallback (Best → Standard) and yearly-add-on
 * gating (no yearly option for monthly base subs).
 *
 * Run with:  pnpm tsx tests/components/LLMTierSelector.test.tsx
 */

import {
  deriveTierVisualState,
  purchaseOptionsForTier,
} from "@/components/session/LLMTierSelector"
import type { LLMUpgradeStatus } from "@/lib/api"


// ── Fixtures ────────────────────────────────────────────────────────────────


export const FREE_USER_STATUS: LLMUpgradeStatus = {
  entitled_tier: "standard",
  better_subscription_active: false,
  best_subscription_active: false,
  better_credits_balance: 0,
  upgraded_resumes_used: 0,
  upgraded_resumes_limit: 100,
  best_soft_cap_hit: false,
  base_billing_cycle: null,
}

export const BETTER_CREDIT_USER_STATUS: LLMUpgradeStatus = {
  entitled_tier: "better",
  better_subscription_active: false,
  best_subscription_active: false,
  better_credits_balance: 5,
  upgraded_resumes_used: 0,
  upgraded_resumes_limit: 100,
  best_soft_cap_hit: false,
  base_billing_cycle: "recurring",
}

export const BEST_MONTHLY_USER_STATUS: LLMUpgradeStatus = {
  entitled_tier: "best",
  better_subscription_active: false,
  best_subscription_active: true,
  better_credits_balance: 0,
  upgraded_resumes_used: 12,
  upgraded_resumes_limit: 100,
  best_soft_cap_hit: false,
  base_billing_cycle: "recurring",
}

export const BEST_YEARLY_USER_STATUS: LLMUpgradeStatus = {
  ...BEST_MONTHLY_USER_STATUS,
  base_billing_cycle: "yearly",
}

export const BEST_SOFT_CAPPED_STATUS: LLMUpgradeStatus = {
  entitled_tier: "standard",
  better_subscription_active: false,
  best_subscription_active: true,
  better_credits_balance: 0,
  upgraded_resumes_used: 100,
  upgraded_resumes_limit: 100,
  best_soft_cap_hit: true,
  base_billing_cycle: "recurring",
}


// ── Test helpers ────────────────────────────────────────────────────────────


function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}


// ── Tests ───────────────────────────────────────────────────────────────────


export function runTests() {
  console.log("\nLLMTierSelector component tests\n")

  // ── 1. Free user ──
  {
    const standard = deriveTierVisualState("standard", FREE_USER_STATUS)
    const better = deriveTierVisualState("better", FREE_USER_STATUS)
    const best = deriveTierVisualState("best", FREE_USER_STATUS)
    assert(standard.runnable, "free → standard is runnable")
    assert(!better.runnable, "free → better is locked")
    assert(!best.runnable, "free → best is locked")
    assert(!best.softCapHit, "free → best is NOT soft-cap-hit")
  }

  // ── 2. Better-credit user (5 credits) ──
  {
    const better = deriveTierVisualState("better", BETTER_CREDIT_USER_STATUS)
    const best = deriveTierVisualState("best", BETTER_CREDIT_USER_STATUS)
    assert(better.runnable, "better-credit → better is runnable")
    assert(
      better.badge === "5 credits remaining",
      "better-credit → badge is '5 credits remaining'",
    )
    assert(!best.runnable, "better-credit → best is still locked")
  }

  // ── 3. Best-subscribed user (monthly base) ──
  {
    const best = deriveTierVisualState("best", BEST_MONTHLY_USER_STATUS)
    assert(best.runnable, "best-monthly → best is runnable")
    assert(!best.softCapHit, "best-monthly → no soft cap")
    assert(
      best.badge === "88 of 100 this period",
      "best-monthly → remaining-of-limit badge",
    )
  }

  // ── 4. Best-subscribed but soft cap hit ──
  {
    const best = deriveTierVisualState("best", BEST_SOFT_CAPPED_STATUS)
    assert(best.softCapHit, "best soft-capped → softCapHit=true")
    assert(!best.runnable, "best soft-capped → not runnable (greyed out)")
    assert(
      best.badge === "Quota reached — using Standard",
      "best soft-capped → quota-reached badge",
    )
  }

  // ── 5. Yearly add-on visibility — monthly base hides yearly options ──
  {
    const opts = purchaseOptionsForTier("better", "recurring")
    const codes = opts.map((o) => o.code)
    assert(codes.includes("better_5pack"), "monthly base → 5-pack visible")
    assert(codes.includes("better_monthly"), "monthly base → monthly visible")
    assert(
      !codes.includes("better_yearly"),
      "monthly base → yearly NOT visible (avoids 409)",
    )
  }

  // ── 6. Yearly base shows yearly add-on for both Better and Best ──
  {
    const better = purchaseOptionsForTier("better", "yearly")
    const best = purchaseOptionsForTier("best", "yearly")
    assert(
      better.some((o) => o.code === "better_yearly"),
      "yearly base → better_yearly visible",
    )
    assert(
      best.some((o) => o.code === "best_yearly"),
      "yearly base → best_yearly visible",
    )
  }

  // ── 7. Best-yearly user can see best_yearly add-on ──
  {
    const opts = purchaseOptionsForTier("best", BEST_YEARLY_USER_STATUS.base_billing_cycle)
    assert(
      opts.length === 3,
      "best-yearly user → 3 purchase options (per-resume / monthly / yearly)",
    )
  }

  // ── 8. Standard tier is always runnable, regardless of status ──
  {
    const a = deriveTierVisualState("standard", null)
    const b = deriveTierVisualState("standard", FREE_USER_STATUS)
    assert(a.runnable && b.runnable, "standard → always runnable")
  }

  console.log("\nAll tests passed.\n")
}

if (
  typeof process !== "undefined" &&
  process.argv[1]?.endsWith("LLMTierSelector.test.tsx")
) {
  runTests()
}
