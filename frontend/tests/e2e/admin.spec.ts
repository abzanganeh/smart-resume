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
import { test, expect } from "@playwright/test"

const BASE = "http://localhost:3000"

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

// ── 3. Full admin login → TOTP → /admin/plans (integration) ──────────────────

test.describe("admin login + TOTP flow → /admin/plans", () => {
  test.skip(
    process.env.PLAYWRIGHT_LIVE !== "true",
    "Set PLAYWRIGHT_LIVE=true and run against a real backend with seeded admin to enable",
  )

  const ADMIN_EMAIL = process.env.TEST_ADMIN_EMAIL ?? "admin@example.com"
  const ADMIN_PASSWORD = process.env.TEST_ADMIN_PASSWORD ?? "changeme"
  const ADMIN_TOTP = process.env.TEST_ADMIN_TOTP ?? ""

  test("admin login → TOTP step → reaches /admin/plans", async ({ page }) => {
    await page.goto(`${BASE}/admin/auth`)

    // ── Step 1: credentials ──
    await page.locator("#email").fill(ADMIN_EMAIL)
    await page.locator("#password").fill(ADMIN_PASSWORD)
    await page.getByRole("button", { name: /Continue/i }).click()

    // ── Step 2: TOTP ──
    await expect(page.locator("#totp")).toBeVisible({ timeout: 10_000 })
    await page.locator("#totp").fill(ADMIN_TOTP)
    await page.getByRole("button", { name: /Verify/i }).click()

    // ── Assertion: landed on plans page ──
    await page.waitForURL(/\/admin\/plans/, { timeout: 15_000 })
    expect(page.url()).toContain("/admin/plans")
    await expect(page.getByText("Plans & Pricing")).toBeVisible()
  })
})

// ── 4. Mocked success flow (without real backend) ─────────────────────────────

test.describe("admin login mocked success → TOTP → /admin/plans", () => {
  test("login step → mocked challenge → TOTP step → mocked token → redirects", async ({ page }) => {
    // Mock login endpoint returning challenge
    await page.route("**/api/admin/auth/login", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ challenge_token: "test-challenge-token", expires_in: 300 }),
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

    // Mock session storage API route
    await page.route("**/api/admin/session", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true }),
        })
      } else {
        await route.continue()
      }
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
