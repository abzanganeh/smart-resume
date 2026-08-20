/**
 * E2E: notification bell, inbox, and preferences.
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

const NOTIFICATION_ITEM = {
  id: "notif-e2e-1",
  type: "application_follow_up",
  category: "application_follow_up",
  channel: "in_app",
  title: "Follow up with Acme",
  body: "It has been 7 days since you applied.",
  data: {},
  read_at: null as string | null,
  scheduled_at: null,
  sent_at: "2026-05-28T10:00:00Z",
  delivery_status: "sent",
  created_at: "2026-05-28T10:00:00Z",
}

const ALL_CATEGORIES = [
  "account_security",
  "payment",
  "subscription",
  "resume",
  "application_follow_up",
  "application_interview",
  "application_nudge",
  "application_offer",
  "job_alerts",
  "data_export",
  "account_closure",
  "admin_announcement",
]

const prefsState = {
  email_enabled_categories: [...ALL_CATEGORIES],
  in_app_enabled_categories: [...ALL_CATEGORIES],
  web_push_enabled: false,
  sms_enabled: false,
  sms_phone: null as string | null,
  sms_phone_verified_at: null as string | null,
  digest_mode: "off" as const,
}

async function mockAuth(page: Page) {
  await page.route(`${API}/api/auth/me`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_USER),
    }),
  )
  await page.route(`${API}/api/dashboard/summary`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        display_name: MOCK_USER.display_name,
        tier: MOCK_USER.tier,
        credit_balance: MOCK_USER.credit_balance,
        next_billing_date: null,
        subscription: null,
        counts: { resumes: 0, applications: 0, saved_jobs: 0 },
        recent_activity: [],
        ats_trend: [],
      }),
    }),
  )
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

async function mockNotificationApis(page: Page) {
  NOTIFICATION_ITEM.read_at = null
  prefsState.email_enabled_categories = [...ALL_CATEGORIES]
  prefsState.in_app_enabled_categories = [...ALL_CATEGORIES]

  await page.route(`${API}/api/notifications/unread-count`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ count: NOTIFICATION_ITEM.read_at ? 0 : 1 }),
    }),
  )

  await page.route(`${API}/api/notifications/preferences`, (route: Route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(prefsState),
      })
    }
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as Partial<typeof prefsState>
      Object.assign(prefsState, body)
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(prefsState),
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/notifications/read-all`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ updated: 1 }),
    }),
  )

  await page.route(`${API}/api/notifications/${NOTIFICATION_ITEM.id}/read`, (route: Route) => {
    NOTIFICATION_ITEM.read_at = "2026-05-28T11:00:00Z"
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ ...NOTIFICATION_ITEM }),
    })
  })

  await page.route(`${API}/api/notifications/${NOTIFICATION_ITEM.id}`, (route: Route) => {
    if (route.request().method() === "DELETE") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/notifications*`, (route: Route) => {
    if (route.request().method() === "GET") {
      const url = new URL(route.request().url())
      const unreadOnly = url.searchParams.get("unread_only") === "true"
      const items =
        unreadOnly && NOTIFICATION_ITEM.read_at ? [] : [{ ...NOTIFICATION_ITEM }]
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ items, total: items.length }),
      })
    }
    return route.continue()
  })
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
      { timeout: 10000 },
    )
  })
})

test.describe("Notifications inbox", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
    await mockNotificationApis(page)
    await login(page)
  })

  test("loads notifications and marks one read", async ({ page }) => {
    await page.goto(`${BASE}/notifications`)
    await expect(page.getByRole("heading", { name: "Notifications" })).toBeVisible({
      timeout: 15_000,
    })
    await expect(page.getByText("Follow up with Acme")).toBeVisible()

    const readPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/notifications/${NOTIFICATION_ITEM.id}/read`) &&
        req.method() === "PATCH",
    )
    await page.getByRole("button", { name: "Follow up with Acme" }).click()
    await readPromise

    await page.getByRole("button", { name: "Unread" }).click()
    await expect(page.getByText("No notifications in this view.")).toBeVisible()
  })

  test("dismiss removes notification from inbox", async ({ page }) => {
    await page.goto(`${BASE}/notifications`)
    await expect(page.getByText("Follow up with Acme")).toBeVisible({ timeout: 15_000 })

    let remaining = 1
    await page.route(`${API}/api/notifications*`, (route: Route) => {
      if (route.request().method() === "GET") {
        const items = remaining ? [{ ...NOTIFICATION_ITEM }] : []
        return route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ items, total: items.length }),
        })
      }
      return route.continue()
    })

    const deletePromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/notifications/${NOTIFICATION_ITEM.id}`) &&
        req.method() === "DELETE",
    )
    remaining = 0
    await page.getByRole("button", { name: "Dismiss" }).click()
    await deletePromise

    await expect(page.getByText("Follow up with Acme")).not.toBeVisible()
  })
})

test.describe("Notification preferences", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
    await mockNotificationApis(page)
    await login(page)
  })

  test("toggle email category PATCHes preferences", async ({ page }) => {
    await page.goto(`${BASE}/settings/notifications`)
    await expect(
      page.getByRole("heading", { name: "Notification preferences" }),
    ).toBeVisible({ timeout: 15_000 })

    const paymentRow = page.getByRole("row", { name: /Payment/i })
    const emailCheckbox = paymentRow.getByRole("checkbox").first()

    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes("/api/notifications/preferences") &&
        req.method() === "PATCH" &&
        !(req.postDataJSON() as { email_enabled_categories?: string[] })
          .email_enabled_categories?.includes("payment"),
    )

    await emailCheckbox.uncheck()
    await patchPromise

    await expect(emailCheckbox).not.toBeChecked()
  })
})
