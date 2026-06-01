/**
 * E2E danger zone — account closure banner (Playwright).
 *
 * Run: pnpm exec playwright test tests/e2e/settings-danger.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const USER_FIXTURE = {
  id: "user-danger-1",
  email: "danger@example.com",
  display_name: "Danger User",
  tier: "free",
  credit_balance: 5,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

async function mockAuth(page: Page) {
  await page.route(`${API}/api/auth/me`, async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(USER_FIXTURE),
    })
  })
}

test.describe("Settings danger zone", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      window.sessionStorage.setItem(
        "next-auth.session-token",
        "mock-session",
      )
    })
  })

  test("close account shows scheduled deletion banner", async ({ page }) => {
    await mockAuth(page)

    await page.route(`${API}/api/account/close`, async (route: Route) => {
      const scheduled = new Date()
      scheduled.setDate(scheduled.getDate() + 30)
      USER_FIXTURE.closure_requested_at = new Date().toISOString()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          scheduled_delete_at: scheduled.toISOString(),
        }),
      })
    })

    await page.route(`${API}/api/auth/me`, async (route: Route) => {
      const scheduled = new Date()
      scheduled.setDate(scheduled.getDate() + 30)
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ...USER_FIXTURE,
          closure_requested_at: new Date().toISOString(),
        }),
      })
    })

    await page.goto(`${BASE}/settings/danger`)

    await expect(page.getByTestId("closure-banner")).toBeVisible()
    await expect(page.getByTestId("closure-banner")).toContainText("Account will be deleted on")
    await expect(page.getByRole("button", { name: "Cancel closure" })).toBeVisible()
  })

  test("close account flow opens confirm dialog", async ({ page }) => {
    await mockAuth(page)

    await page.goto(`${BASE}/settings/danger`)

    await page.getByRole("button", { name: "Close my account" }).click()
    await expect(page.getByText("Download your data first?")).toBeVisible()

    await page.getByRole("button", { name: "Skip export" }).click()
    await expect(page.getByText("Confirm account closure")).toBeVisible()
    await expect(page.getByTestId("delete-confirm-input")).toBeVisible()
  })
})
