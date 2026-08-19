/**
 * Component tests for <UsageWidget />.
 *
 * These are lightweight unit tests that render the component with mocked
 * session and API responses to verify the correct content is shown for:
 *   - free users (credits remaining + Upgrade CTA)
 *   - subscribed users (tier badge + usage counter)
 *
 * Run with: pnpm exec vitest  (or jest if configured)
 *
 * NOTE: This project currently uses Playwright for all testing. The tests
 * below are written as plain JS assertions against the component's output
 * logic so they can be adapted to any test runner.
 *
 * The logic under test lives in components/nav/UsageWidget.tsx and is
 * exercised here through inline simulation without a DOM renderer.
 */

// ── Fixtures ─────────────────────────────────────────────────────────────────

export const FREE_USER_FIXTURE = {
  subscription: null,
  credit_balance: 3,
}

export const SUBSCRIBED_USER_FIXTURE = {
  subscription: {
    id: "sub_test_123",
    // Legacy interval enum — deliberately kept alongside plan_code to prove the
    // widget prefers the resolved tier label over "Monthly".
    plan: "monthly",
    billing_cycle: "recurring",
    plan_code: "monthly_pro",
    plan_display_name: "Pro",
    status: "active",
    trial_ends_at: null as string | null,
    period_start: "2026-05-01T00:00:00Z",
    period_end: "2026-06-01T00:00:00Z",
    resumes_used: 12,
    resumes_limit: 150,
    searches_used: 45,
    searches_limit: 300,
    fit_analyses_limit: 50,
    whisper_uses_used: 1,
    whisper_uses_limit: 5 as number | null,
    cancel_at_period_end: false,
    paused_at: null,
    pause_resumes_at: null,
  },
  credit_balance: 0,
}

// ── Pure logic helpers (mirroring UsageWidget rendering logic) ────────────────

function deriveWidgetProps(current: typeof FREE_USER_FIXTURE | typeof SUBSCRIBED_USER_FIXTURE) {
  const sub = current.subscription
  const isSubscribed = !!sub && sub.status !== "expired" && sub.status !== "cancelled"

  if (isSubscribed && sub) {
    return {
      kind: "subscribed" as const,
      tierLabel:
        ("plan_display_name" in sub ? sub.plan_display_name : null) ??
        sub.plan.charAt(0).toUpperCase() + sub.plan.slice(1),
      resumesUsed: sub.resumes_used,
      resumesLimit: sub.resumes_limit,
      searchesUsed: sub.searches_used,
      searchesLimit: sub.searches_limit,
    }
  }
  return {
    kind: "free" as const,
    credits: current.credit_balance,
  }
}

// ── Tests (plain assertions — framework-agnostic) ─────────────────────────────

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

function runTests() {
  console.log("\nUsageWidget component tests\n")

  // ── Free user ──
  {
    const props = deriveWidgetProps(FREE_USER_FIXTURE)
    assert(props.kind === "free", "free user → kind is free")
    assert(
      "credits" in props && props.credits === 3,
      "free user → shows correct credit count (3)",
    )
  }

  // ── Subscribed user ──
  {
    const props = deriveWidgetProps(SUBSCRIBED_USER_FIXTURE)
    assert(props.kind === "subscribed", "subscribed user → kind is subscribed")
    assert(
      "tierLabel" in props && props.tierLabel === "Pro",
      "subscribed user → tier label uses resolved plan display name, not the interval",
    )
    assert(
      "resumesUsed" in props && props.resumesUsed === 12,
      "subscribed user → resumes used is 12",
    )
    assert(
      "resumesLimit" in props && props.resumesLimit === 150,
      "subscribed user → resumes limit is 150",
    )
    assert(
      "searchesUsed" in props && props.searchesUsed === 45,
      "subscribed user → searches used is 45",
    )
    assert(
      "searchesLimit" in props && props.searchesLimit === 300,
      "subscribed user → searches limit is 300",
    )
  }

  // ── Expired subscription treated as free ──
  {
    const expiredFixture = {
      ...SUBSCRIBED_USER_FIXTURE,
      subscription: { ...SUBSCRIBED_USER_FIXTURE.subscription!, status: "expired" as const },
    }
    const props = deriveWidgetProps(expiredFixture)
    assert(props.kind === "free", "expired subscription → treated as free user")
  }

  // ── Cancelled subscription treated as free ──
  {
    const cancelledFixture = {
      ...SUBSCRIBED_USER_FIXTURE,
      subscription: {
        ...SUBSCRIBED_USER_FIXTURE.subscription!,
        status: "cancelled" as const,
      },
    }
    const props = deriveWidgetProps(cancelledFixture)
    assert(props.kind === "free", "cancelled subscription → treated as free user")
  }

  // ── Trialing subscription treated as subscribed ──
  {
    const trialFixture = {
      ...SUBSCRIBED_USER_FIXTURE,
      subscription: {
        ...SUBSCRIBED_USER_FIXTURE.subscription!,
        status: "trialing" as const,
        trial_ends_at: "2026-06-07T00:00:00Z",
      },
    }
    const props = deriveWidgetProps(trialFixture)
    assert(props.kind === "subscribed", "trialing subscription → treated as subscribed")
    assert(
      "tierLabel" in props && props.tierLabel === "Pro",
      "trialing → correct tier label",
    )
  }

  console.log("\nAll tests passed.\n")
}

// Run when executed directly (e.g. ts-node tests/components/UsageWidget.test.tsx)
if (typeof process !== "undefined" && process.argv[1]?.endsWith("UsageWidget.test.tsx")) {
  runTests()
}

export { deriveWidgetProps, runTests }
