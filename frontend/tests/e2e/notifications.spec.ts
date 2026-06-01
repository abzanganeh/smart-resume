/**
 * E2E: notification unread badge reflects /api/notifications/unread-count.
 *
 * Run: pnpm exec playwright test tests/e2e/notifications.spec.ts
 */
import { test, expect } from "@playwright/test"

const API = "http://localhost:8000"

test.describe("Notification bell", () => {
  test("unread count badge updates after count increases", async ({ page }) => {
    let polls = 0
    await page.route(`${API}/api/notifications/unread-count`, async (route) => {
      polls += 1
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ count: polls >= 2 ? 1 : 0 }),
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

    await page.goto("http://localhost:3000/dashboard")
    const bell = page.getByLabel("Notifications")
    const visible = await bell.isVisible().catch(() => false)
    if (!visible) {
      test.skip(true, "Requires authenticated session on /dashboard")
    }

    await expect(page.locator('button[aria-label="Notifications"] span')).toHaveCount(0)

    await page.reload()
    await expect(page.locator('button[aria-label="Notifications"] span')).toHaveText(
      "1",
      { timeout: 10000 }
    )
  })
})
