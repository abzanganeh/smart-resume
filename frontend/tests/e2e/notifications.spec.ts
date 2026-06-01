/**
 * E2E: notification unread badge updates after a new notification exists.
 *
 * Run: pnpm exec playwright test tests/e2e/notifications.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"
const MOCK_ACCESS = "mock-access-token-notifications"
const MOCK_USER = {
  id: "user-notifications-e2e",
  email: "notifications-e2e@example.com",
  display_name: "Notif User",
  tier: "free",
  credit_balance: 5,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

async function mockAuth(page: Page) {
  await page.route(`${API}/api/auth/login`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: MOCK_ACCESS,
        token_type: "bearer",
        expires_in: 900,
        user: MOCK_USER,
      }),
    }),
  )
}

async function login(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill(MOCK_USER.email)
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

test.describe("Notification bell", () => {
  test("unread count badge updates after count increases on next 60s poll", async ({ page }) => {
    test.setTimeout(90_000)
    await mockAuth(page)
    const startMs = Date.now()
    await page.route(`${API}/api/notifications/unread-count`, async (route) => {
      const hasNewNotification = Date.now() - startMs >= 3_000
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ count: hasNewNotification ? 1 : 0 }),
      })
    })
    await page.route(`${API}/api/notifications`, async (route) => {
      if (route.request().method() === "GET") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items: [], total: 0 }),
        })
        return
      }
      await route.continue()
    })

    await login(page)

    await expect(page.getByLabel("Notifications")).toBeVisible({ timeout: 10_000 })
    await expect(page.locator('button[aria-label="Notifications"] span')).toHaveCount(0)

    // Poll interval in NotificationBell is fixed at 60 seconds.
    await page.waitForTimeout(61_000)
    await expect(page.locator('button[aria-label="Notifications"] span')).toHaveText(
      "1",
      { timeout: 10000 }
    )
  })
})
