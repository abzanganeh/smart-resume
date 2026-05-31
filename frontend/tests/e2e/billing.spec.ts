/**
 * E2E billing tests (Playwright).
 *
 * Most tests mock the backend API so they run without a live server.
 * The "PLAYWRIGHT_LIVE=true" group requires a real backend + Stripe test mode.
 *
 * Run: pnpm exec playwright test tests/e2e/billing.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

// ── Fixtures ──────────────────────────────────────────────────────────────────

const PRICES_FIXTURE = {
  version: "plans-test",
  currency: "USD",
  plans: [
    {
      code: "daily",
      display_name: "Daily",
      cycle: "daily",
      amount_cents: 299,
      trial_days: null,
      stripe_price_id: "price_daily_test",
      is_active: true,
      features: ["resume_tailor"],
    },
    {
      code: "weekly",
      display_name: "Weekly",
      cycle: "weekly",
      amount_cents: 999,
      trial_days: null,
      stripe_price_id: "price_weekly_test",
      is_active: true,
      features: ["resume_tailor", "cover_letter"],
    },
    {
      code: "monthly",
      display_name: "Monthly",
      cycle: "monthly",
      amount_cents: 1999,
      trial_days: 7,
      stripe_price_id: "price_monthly_test",
      is_active: true,
      features: ["resume_tailor", "cover_letter", "fit_analysis", "job_search"],
    },
  ],
  addons: [],
}

const SUB_CURRENT_FREE_FIXTURE = {
  subscription: null,
  credit_balance: 3,
}

// ── Helpers ───────────────────────────────────────────────────────────────────

async function mockBillingApis(page: Page, subFixture: object = SUB_CURRENT_FREE_FIXTURE) {
  await page.route(`${API}/api/billing/prices`, (route: Route) =>
    route.fulfill({ json: PRICES_FIXTURE, status: 200 }),
  )
  await page.route(`${API}/api/subscriptions/current`, (route: Route) =>
    route.fulfill({ json: subFixture, status: 200 }),
  )
}

// ── Guard redirect ────────────────────────────────────────────────────────────

test.describe("billing route guard", () => {
  test("GET /billing → redirects unauthenticated users to /auth", async ({ page }) => {
    await page.goto(`${BASE}/billing`)
    await page.waitForURL(/\/auth/)
    expect(page.url()).toContain("/auth")
    expect(new URL(page.url()).searchParams.get("callbackUrl")).toBeTruthy()
  })
})

// ── Cancel page ───────────────────────────────────────────────────────────────

test.describe("/billing/cancel page", () => {
  test("shows 'Not ready?' message and link back to billing", async ({ page }) => {
    await page.goto(`${BASE}/billing/cancel`)
    await expect(page.getByText(/Not ready/)).toBeVisible()
    await expect(page.getByRole("link", { name: /View plans/i })).toBeVisible()
    const href = await page
      .getByRole("link", { name: /View plans/i })
      .getAttribute("href")
    expect(href).toContain("/billing")
  })
})

test.describe("/billing/success page", () => {
  test("unauthenticated users are prompted to sign in for verification", async ({ page }) => {
    await page.goto(`${BASE}/billing/success`)
    await expect(page.getByText(/Sign in to confirm billing status/i)).toBeVisible()
    await expect(page.getByRole("link", { name: /Sign in/i })).toBeVisible()
    const href = await page.getByRole("link", { name: /Sign in/i }).getAttribute("href")
    expect(href).toContain("/auth")
    expect(href).toContain("callbackUrl=/billing/success")
  })
})

// ── Live / integration tests (require real backend + Stripe test mode) ────────

test.describe("billing checkout redirect", () => {
  test.skip(
    process.env.PLAYWRIGHT_LIVE !== "true",
    "Set PLAYWRIGHT_LIVE=true and run against a real backend+Stripe to enable this test",
  )

  test("clicking Subscribe redirects to a Stripe-looking checkout URL", async ({ page }) => {
    // Sign in first
    await page.goto(`${BASE}/auth`)
    await page.getByPlaceholder("you@example.com").fill(process.env.E2E_EMAIL ?? "")
    await page.getByPlaceholder("••••••••••").fill(process.env.E2E_PASSWORD ?? "")
    await page.getByRole("button", { name: "Sign in" }).click()
    await page.waitForURL(/\/session\/new|\/onboarding|\/billing/, { timeout: 15_000 })

    // Navigate to billing
    await page.goto(`${BASE}/billing`)
    await page.waitForSelector("text=Choose a plan", { timeout: 10_000 })

    // Click the first Subscribe button
    const subscribeBtn = page.getByRole("button", { name: /Subscribe/i }).first()
    await subscribeBtn.click()

    // Should redirect to Stripe checkout (stripe.com or mock stripe URL)
    await page.waitForURL(/stripe\.com|checkout\.stripe\.com|localhost.*stripe/i, {
      timeout: 15_000,
    })
    expect(page.url()).toMatch(/stripe/i)
  })
})

// ── Mock-based checkout test ──────────────────────────────────────────────────

test.describe("billing page (mocked backend)", () => {
  test.skip(
    // These tests work without a live backend by mocking the API layer
    // but still require an authenticated session which is hard to fake
    // without backend token exchange — mark them as live-only for now
    process.env.PLAYWRIGHT_LIVE !== "true",
    "Requires authenticated session — set PLAYWRIGHT_LIVE=true",
  )

  test("Subscribe button calls checkout and follows redirect URL", async ({ page }) => {
    const MOCK_CHECKOUT_URL = "https://checkout.stripe.com/pay/cs_test_mock"

    await mockBillingApis(page, SUB_CURRENT_FREE_FIXTURE)
    await page.route(`${API}/api/subscriptions/checkout`, (route: Route) =>
      route.fulfill({ json: { checkout_url: MOCK_CHECKOUT_URL }, status: 200 }),
    )

    await page.goto(`${BASE}/billing`)
    await page.waitForSelector("text=Choose a plan", { timeout: 10_000 })

    await page.getByRole("button", { name: /Subscribe/i }).first().click()
    await page.waitForURL(MOCK_CHECKOUT_URL, { timeout: 10_000 })
    expect(page.url()).toBe(MOCK_CHECKOUT_URL)
  })
})
