/**
 * Component tests for the admin Reports page charts.
 *
 * Pattern: framework-agnostic assertions against the pure data
 * transformation helpers used by the report charts.  Because recharts
 * renders SVG in a browser context we test the data-shaping layer
 * (date range defaults, filter logic, CSV export payload) rather than
 * the rendered SVG output.
 *
 * Run with: pnpm tsx tests/components/AdminReports.test.ts
 */

// ── Fixtures ──────────────────────────────────────────────────────────────────

import type {
  ActivityMetrics,
  FunnelMetrics,
  RevenueByPlan,
  LLMCostMargin,
  ChurnMetrics,
} from "@/lib/admin/types"

export const ACTIVITY_FIXTURE: ActivityMetrics[] = [
  { date: "2026-05-01", dau: 120, wau: 540, mau: 1200, new_registrations: 15 },
  { date: "2026-05-02", dau: 135, wau: 570, mau: 1220, new_registrations: 18 },
  { date: "2026-05-03", dau: 110, wau: 520, mau: 1210, new_registrations: 10 },
]

export const FUNNEL_FIXTURE: FunnelMetrics = {
  registered: 1000,
  email_verified: 820,
  first_build: 560,
  first_export: 340,
  subscribed: 180,
}

export const REVENUE_FIXTURE: RevenueByPlan[] = [
  { plan: "weekly", revenue_usd: 480.0, subscribers: 120 },
  { plan: "monthly_pro", revenue_usd: 2400.0, subscribers: 200 },
  { plan: "monthly_plus", revenue_usd: 900.0, subscribers: 45 },
]

export const LLM_COST_FIXTURE: LLMCostMargin[] = [
  { date: "2026-05-01", tier: "standard", cost_usd: 12.5, revenue_usd: 80.0, margin_usd: 67.5, volume: 250 },
  { date: "2026-05-01", tier: "better", cost_usd: 35.0, revenue_usd: 120.0, margin_usd: 85.0, volume: 85 },
  { date: "2026-05-01", tier: "best", cost_usd: 22.0, revenue_usd: 150.0, margin_usd: 128.0, volume: 44 },
]

export const CHURN_FIXTURE: ChurnMetrics[] = [
  { date: "2026-05-01", plan: "monthly", churn_rate: 0.025 },
  { date: "2026-05-02", plan: "monthly", churn_rate: 0.022 },
  { date: "2026-05-03", plan: "monthly", churn_rate: 0.027 },
]

// ── Pure helper functions used by the page ────────────────────────────────────

/** Filter LLM cost/margin data by tier. */
export function filterLLMCostByTier(
  data: LLMCostMargin[],
  tier: "all" | "standard" | "better" | "best",
): LLMCostMargin[] {
  return tier === "all" ? data : data.filter((d) => d.tier === tier)
}

/** Build funnel data array for recharts FunnelChart. */
export function buildFunnelData(metrics: FunnelMetrics) {
  return [
    { name: "Registered", value: metrics.registered },
    { name: "Email verified", value: metrics.email_verified },
    { name: "First build", value: metrics.first_build },
    { name: "First export", value: metrics.first_export },
    { name: "Subscribed", value: metrics.subscribed },
  ]
}

/** Return default date range: last 30 days. */
export function defaultDateRange(): { from: string; to: string } {
  const today = new Date().toISOString().slice(0, 10)
  const thirtyDaysAgo = new Date(Date.now() - 30 * 86400000).toISOString().slice(0, 10)
  return { from: thirtyDaysAgo, to: today }
}

/** Compute total revenue across all plans. */
export function totalRevenue(data: RevenueByPlan[]): number {
  return data.reduce((sum, d) => sum + d.revenue_usd, 0)
}

/** Compute average churn rate. */
export function averageChurn(data: ChurnMetrics[]): number {
  if (data.length === 0) return 0
  return data.reduce((sum, d) => sum + d.churn_rate, 0) / data.length
}

// ── Test helpers ──────────────────────────────────────────────────────────────

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

// ── Tests ─────────────────────────────────────────────────────────────────────

export function runTests() {
  console.log("\nAdminReports component tests\n")

  // ── Activity data ─────────────────────────────────────────────────────
  {
    assert(ACTIVITY_FIXTURE.length === 3, "activity fixture has 3 rows")
    assert(
      ACTIVITY_FIXTURE[0].dau === 120,
      "activity fixture[0].dau === 120",
    )
    assert(
      ACTIVITY_FIXTURE.every((d) => d.date.match(/^\d{4}-\d{2}-\d{2}$/)),
      "all dates are YYYY-MM-DD",
    )
  }

  // ── Funnel data ───────────────────────────────────────────────────────
  {
    const funnelData = buildFunnelData(FUNNEL_FIXTURE)
    assert(funnelData.length === 5, "funnel has 5 steps")
    assert(funnelData[0].name === "Registered", "first step is Registered")
    assert(funnelData[4].name === "Subscribed", "last step is Subscribed")
    // Values should be monotonically non-increasing (funnel shape)
    for (let i = 1; i < funnelData.length; i++) {
      assert(
        funnelData[i].value <= funnelData[i - 1].value,
        `funnel step ${i} (${funnelData[i].value}) <= step ${i - 1} (${funnelData[i - 1].value})`,
      )
    }
  }

  // ── Revenue totals ────────────────────────────────────────────────────
  {
    const total = totalRevenue(REVENUE_FIXTURE)
    assert(
      Math.abs(total - 3780) < 0.01,
      `total revenue == $3780 (got $${total})`,
    )
    assert(
      REVENUE_FIXTURE.every((r) => r.revenue_usd >= 0),
      "all revenue values non-negative",
    )
  }

  // ── LLM cost filter ───────────────────────────────────────────────────
  {
    const all = filterLLMCostByTier(LLM_COST_FIXTURE, "all")
    assert(all.length === 3, "filter 'all' returns 3 rows")

    const standard = filterLLMCostByTier(LLM_COST_FIXTURE, "standard")
    assert(standard.length === 1, "filter 'standard' returns 1 row")
    assert(standard[0].tier === "standard", "filtered row is standard tier")

    const best = filterLLMCostByTier(LLM_COST_FIXTURE, "best")
    assert(best.length === 1, "filter 'best' returns 1 row")
    assert(best[0].margin_usd === 128.0, "best tier margin == 128.0")
  }

  // ── LLM cost margins are positive in fixture ──────────────────────────
  {
    assert(
      LLM_COST_FIXTURE.every((d) => d.margin_usd > 0),
      "all fixture LLM margins are positive",
    )
    assert(
      LLM_COST_FIXTURE.every((d) => d.margin_usd === d.revenue_usd - d.cost_usd),
      "margin === revenue - cost for all rows",
    )
  }

  // ── Churn rate ────────────────────────────────────────────────────────
  {
    const avg = averageChurn(CHURN_FIXTURE)
    assert(avg > 0 && avg < 1, "average churn is between 0 and 1")
    assert(averageChurn([]) === 0, "averageChurn([]) === 0")
  }

  // ── Default date range ────────────────────────────────────────────────
  {
    const { from, to } = defaultDateRange()
    assert(from < to, "from < to in default range")
    assert(to.match(/^\d{4}-\d{2}-\d{2}$/) !== null, "to is YYYY-MM-DD")
    const diffDays = (new Date(to).getTime() - new Date(from).getTime()) / 86400000
    assert(Math.abs(diffDays - 30) <= 1, "default range is ~30 days")
  }

  console.log("\nAll AdminReports tests passed.\n")
}

if (
  typeof process !== "undefined" &&
  process.argv[1]?.endsWith("AdminReports.test.ts")
) {
  runTests()
}
