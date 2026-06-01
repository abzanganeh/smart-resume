/**
 * E2E: settings danger zone export + closure workflow.
 *
 * Run: pnpm exec playwright test tests/e2e/settings-danger.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"
const MOCK_ACCESS = "mock-access-token-danger"
const USER_FIXTURE = {
  id: "user-danger-e2e",
  email: "danger-e2e@example.com",
  display_name: "Danger User",
  tier: "free",
  credit_balance: 5,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null as string | null,
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
        user: USER_FIXTURE,
      }),
    }),
  )
}

async function login(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill(USER_FIXTURE.email)
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

test.describe("Settings danger zone", () => {
  test("download data polls and renders download link", async ({ page }) => {
    test.setTimeout(20_000)
    await mockAuth(page)

    await page.route(`${API}/api/auth/me`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(USER_FIXTURE),
      })
    })

    await page.route(`${API}/api/account/export`, async (route: Route) => {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({ job_id: "job-e2e-1" }),
      })
    })

    let pollCount = 0
    await page.route(`${API}/api/account/export/job-e2e-1`, async (route: Route) => {
      pollCount += 1
      const isReady = pollCount >= 2
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "job-e2e-1",
          status: isReady ? "ready" : "processing",
          presigned_url: isReady ? "https://s3.example.com/export.zip?sig=e2e" : null,
          presigned_url_expires_at: "2026-06-30T00:00:00Z",
          error: null,
          created_at: "2026-05-31T00:00:00Z",
          completed_at: isReady ? "2026-05-31T00:00:05Z" : null,
        }),
      })
    })

    await login(page)
    await page.goto(`${BASE}/settings/danger`)
    await page.getByRole("button", { name: "Download my data" }).click()
    await expect(page.getByTestId("export-download-link")).toBeVisible({ timeout: 12_000 })
  })

  test("close account requires DELETE and shows scheduled banner", async ({ page }) => {
    await mockAuth(page)

    await page.route(`${API}/api/auth/me`, async (route: Route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(USER_FIXTURE),
      })
    })

    let scheduledIso = ""
    await page.route(`${API}/api/account/close`, async (route: Route) => {
      const scheduled = new Date()
      scheduled.setDate(scheduled.getDate() + 30)
      scheduledIso = scheduled.toISOString()
      USER_FIXTURE.closure_requested_at = new Date().toISOString()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          scheduled_delete_at: scheduledIso,
        }),
      })
    })

    await login(page)
    await page.goto(`${BASE}/settings/danger`)
    await page.getByRole("button", { name: "Close my account" }).click()
    await expect(page.getByText("Download your data first?")).toBeVisible()
    await page.getByRole("button", { name: "Skip export" }).click()
    await expect(page.getByText("Confirm account closure")).toBeVisible()

    const scheduleButton = page.getByRole("button", { name: "Schedule deletion" })
    await expect(scheduleButton).toBeDisabled()
    await page.getByTestId("delete-confirm-input").fill("DELETE")
    await expect(scheduleButton).toBeEnabled()
    await scheduleButton.click()

    await expect(page.getByTestId("closure-banner")).toBeVisible()
    await expect(page.getByTestId("closure-banner")).toContainText("Account will be deleted on")
    expect(scheduledIso).not.toBe("")
  })
})
