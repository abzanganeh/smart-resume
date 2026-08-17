/**
 * E2E application tracker tests (Playwright).
 *
 * Run: pnpm exec playwright test tests/e2e/tracker.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const APP_ID = "app-e2e-1"

const APPLICATIONS_FIXTURE = [
  {
    id: APP_ID,
    resume_record_id: null,
    jd_title: "Software Engineer",
    jd_company: "Beta Corp",
    status: "applied",
    applied_date: "2026-05-28T10:00:00Z",
    follow_up_date: null,
    created_at: "2026-05-28T10:00:00Z",
    updated_at: "2026-05-28T10:00:00Z",
  },
]

const MOCK_ACCESS = "mock-access-token-tracker"
const MOCK_USER = {
  id: "user-tracker-e2e",
  email: "tracker-e2e@example.com",
  display_name: "Tracker User",
  tier: "free",
  credit_balance: 5,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  onboarding_completed_at: "2026-05-01T00:00:00Z",
  onboarding_ai_choice: "platform",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

let patchedStatus: string | null = null

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

async function login(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill(MOCK_USER.email)
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

async function mockTrackerApis(page: Page) {
  patchedStatus = null

  await page.route(`${API}/api/resumes*`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }),
    }),
  )

  await page.route(`${API}/api/applications`, (route: Route) => {
    if (route.request().method() === "GET") {
      const items = APPLICATIONS_FIXTURE.map((a) =>
        patchedStatus ? { ...a, status: patchedStatus } : a,
      )
      return route.fulfill({ json: items, status: 200 })
    }
    return route.continue()
  })

  await page.route(`${API}/api/applications/${APP_ID}`, (route: Route) => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as { status?: string }
      patchedStatus = body.status ?? patchedStatus
      return route.fulfill({
        json: { ...APPLICATIONS_FIXTURE[0], status: patchedStatus ?? "applied" },
        status: 200,
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/resumes*`, (route: Route) =>
    route.fulfill({
      json: { items: [], total: 0, page: 1, page_size: 100 },
      status: 200,
    }),
  )
}

test.describe("tracker route guard", () => {
  test("GET /tracker → redirects unauthenticated users to /auth", async ({ page }) => {
    await page.goto(`${BASE}/tracker`)
    await page.waitForURL(/\/auth/)
    expect(page.url()).toContain("/auth")
  })
})

test.describe("tracker kanban (mocked API)", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
    await mockTrackerApis(page)
    await login(page)
    await page.goto(`${BASE}/tracker`)
    await expect(page.getByRole("heading", { name: /Application tracker/i })).toBeVisible({
      timeout: 15_000,
    })
  })

  test("drag card from Applied to Interviewing updates status via PATCH", async ({
    page,
  }) => {
    const card = page.getByTestId(`app-card-${APP_ID}`)
    await expect(card).toBeVisible()
    await expect(card).toHaveAttribute("data-status", "applied")

    const interviewingColumn = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Interviewing" }) })

    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/applications/${APP_ID}`) &&
        req.method() === "PATCH" &&
        (req.postDataJSON() as { status?: string }).status === "interviewing",
    )

    await card.dragTo(interviewingColumn)
    const patchReq = await patchPromise
    expect((patchReq.postDataJSON() as { status: string }).status).toBe("interviewing")

    await expect(card).toHaveAttribute("data-status", "interviewing")
  })
})
