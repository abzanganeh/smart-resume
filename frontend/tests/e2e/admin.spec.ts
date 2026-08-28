/**
 * E2E tests for the /admin panel (Playwright).
 *
 * These tests cover:
 *   1. Non-admin redirect: unauthenticated user → /admin/auth
 *   2. Admin login → TOTP step → reaches /admin/plans
 *
 * The "full flow" test requires PLAYWRIGHT_LIVE=true with a running backend.
 * The redirect test works against the Next.js dev server alone.
 *
 * Run: pnpm exec playwright test tests/e2e/admin.spec.ts
 */
import { test, expect, type Page } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const ADMIN_SESSION = {
  access_token: "mock-admin-token",
  admin: {
    id: "00000000-0000-0000-0000-000000000001",
    email: "admin@test.com",
    display_name: "Test Admin",
    role: "super-admin",
  },
  expires_in: 3600,
}

async function seedAdminSession(page: Page) {
  await page.request.post(`${BASE}/api/admin/session`, { data: ADMIN_SESSION })
}

async function mockAdminSectionApis(page: Page) {
  await page.route("**/api/admin/plans", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    }
    return route.continue()
  })
  await page.route("**/api/admin/plans/history", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  )
  await page.route("**/api/admin/users**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ users: [], total: 0 }),
    }),
  )
  await page.route("**/api/admin/feature-flags**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ flags: [] }),
    }),
  )
  await page.route("**/api/admin/llm/steps**", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      })
    }
    return route.continue()
  })
  await page.route("**/api/admin/llm/history", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  )
  await page.route("**/api/admin/llm", async (route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ configs: [], similarity_threshold: 0.72 }),
      })
    }
    return route.continue()
  })
  await page.route("**/api/admin/announcements**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ announcements: [] }),
    }),
  )
  await page.route("**/api/admin/refunds**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ refunds: [], total: 0 }),
    }),
  )
  await page.route("**/api/admin/reports/system-health", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        checked_at: "2026-05-28T10:00:00Z",
        stripe_webhook_failed_24h: 0,
      }),
    }),
  )
  await page.route("**/api/admin/reports/activity**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ metrics: [] }),
    }),
  )
  await page.route("**/api/admin/audit-log**", async (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [] }),
    }),
  )
}

const ADMIN_SECTIONS = [
  { path: "/admin/plans", heading: "Plans & Pricing" },
  { path: "/admin/users", heading: "User Management" },
  { path: "/admin/flags", heading: "Feature Flags" },
  { path: "/admin/llm", heading: "LLM Configuration" },
  { path: "/admin/announcements", heading: "Announcements" },
  { path: "/admin/refunds", heading: "Refund Requests" },
  { path: "/admin/system", heading: "System Health" },
  { path: "/admin/audit", heading: "Audit Log" },
  { path: "/admin/reports", heading: "Reports" },
] as const

// ── 1. Unauthenticated redirect ───────────────────────────────────────────────

test.describe("/admin route protection", () => {
  const adminRoutes = [
    "/admin",
    "/admin/plans",
    "/admin/llm",
    "/admin/flags",
    "/admin/announcements",
    "/admin/users",
    "/admin/refunds",
    "/admin/reports",
    "/admin/system",
    "/admin/audit",
  ]

  for (const route of adminRoutes) {
    test(`GET ${route} → redirects to /admin/auth when unauthenticated`, async ({ page }) => {
      await page.goto(`${BASE}${route}`)
      await page.waitForURL(/\/admin\/auth/)
      expect(page.url()).toContain("/admin/auth")
    })
  }

  test("standard user token cannot access /admin/*", async ({ page, context }) => {
    await context.addCookies([
      {
        name: "authjs.session-token",
        value: "regular-user-session-token",
        url: BASE,
      },
    ])
    await page.goto(`${BASE}/admin/users`)
    await page.waitForURL(/\/admin\/auth/)
    expect(page.url()).toContain("/admin/auth")
  })
})

// ── 2. /admin/auth page renders ───────────────────────────────────────────────

test.describe("/admin/auth page", () => {
  test("renders email and password fields", async ({ page }) => {
    await page.goto(`${BASE}/admin/auth`)
    await expect(page.locator("#email")).toBeVisible()
    await expect(page.locator("#password")).toBeVisible()
    await expect(page.getByRole("button", { name: /Continue/i })).toBeVisible()
  })

  test("shows Admin Sign-in heading", async ({ page }) => {
    await page.goto(`${BASE}/admin/auth`)
    await expect(page.getByText("Admin Sign-in")).toBeVisible()
  })

  test("shows session-expired message when reason=expired", async ({ page }) => {
    await page.goto(`${BASE}/admin/auth?reason=expired`)
    await expect(
      page.getByText(/session has expired/i),
    ).toBeVisible()
  })

  test("shows step indicators for 2-factor flow", async ({ page }) => {
    await page.goto(`${BASE}/admin/auth`)
    // Step 1 dot should be visible (active)
    const dots = page.locator("div.rounded-full").filter({ hasText: /^[12]$/ })
    await expect(dots.first()).toBeVisible()
  })

  test("invalid credentials show error from backend", async ({ page }) => {
    // We mock the backend response for this test
    await page.route("**/api/admin/auth/login", async (route) => {
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: JSON.stringify({ detail: { code: "invalid_credentials" } }),
      })
    })

    await page.goto(`${BASE}/admin/auth`)
    await page.locator("#email").fill("wrong@example.com")
    await page.locator("#password").fill("wrong-password")
    await page.getByRole("button", { name: /Continue/i }).click()

    await expect(page.getByText(/Invalid email or password/i)).toBeVisible()
  })
})

// ── 3. Mocked success flow (without real backend) ─────────────────────────────

test.describe("admin login + TOTP flow → /admin/plans", () => {
  test("login step → mocked challenge → TOTP step → mocked token → redirects", async ({ page }) => {
    // Mock login endpoint returning challenge
    await page.route("**/api/admin/auth/login", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          status: "totp_required",
          challenge_token: "test-challenge-token",
          expires_in: 300,
        }),
      })
    })

    // Mock TOTP verify returning admin session
    await page.route("**/api/admin/auth/2fa/verify", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          access_token: "test-admin-jwt",
          expires_in: 3600,
          admin: {
            id: "00000000-0000-0000-0000-000000000001",
            email: "admin@test.com",
            display_name: "Test Admin",
            role: "super-admin",
          },
        }),
      })
    })

    await page.goto(`${BASE}/admin/auth`)

    // ── Step 1 ──
    await page.locator("#email").fill("admin@test.com")
    await page.locator("#password").fill("password")
    await page.getByRole("button", { name: /Continue/i }).click()

    // ── Step 2 ──
    await expect(page.locator("#totp")).toBeVisible({ timeout: 5_000 })
    await page.locator("#totp").fill("123456")
    await page.getByRole("button", { name: /Verify/i }).click()

    // Should redirect to /admin/plans (or be on it)
    await page.waitForURL(/\/admin\/plans/, { timeout: 10_000 })
    expect(page.url()).toContain("/admin/plans")
  })
})

// ── 4. Reports charts render with fixture data ────────────────────────────────

test.describe("/admin/reports chart rendering", () => {
  test("renders recharts surfaces in visual DOM with mocked data", async ({ page }) => {
    await seedAdminSession(page)

    await page.route("**/api/admin/reports/activity**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          metrics: [
            { date: "2026-05-01", dau: 120, wau: 540, mau: 1200, new_registrations: 15 },
            { date: "2026-05-02", dau: 135, wau: 560, mau: 1210, new_registrations: 18 },
          ],
        }),
      })
    })

    await page.goto(`${BASE}/admin/reports`)
    await expect(page.getByText("DAU/WAU/MAU")).toBeVisible()
    await expect(page.locator("svg.recharts-surface").first()).toBeVisible()
  })
})

test.describe("admin section smoke (mocked API)", () => {
  test.beforeEach(async ({ page }) => {
    await seedAdminSession(page)
    await mockAdminSectionApis(page)
  })

  for (const { path, heading } of ADMIN_SECTIONS) {
    test(`${path} loads ${heading}`, async ({ page }) => {
      await page.goto(`${BASE}${path}`)
      await expect(page.getByRole("heading", { name: heading })).toBeVisible({
        timeout: 15_000,
      })
    })
  }
})
