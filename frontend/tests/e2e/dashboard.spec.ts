/**
 * E2E dashboard tests (Playwright).
 *
 * Run: pnpm exec playwright test tests/e2e/dashboard.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const SUMMARY_FIXTURE = {
  display_name: "Test User",
  tier: "free",
  credit_balance: 5,
  next_billing_date: null,
  subscription: null,
  counts: { resumes: 2, applications: 0, saved_jobs: 1 },
  recent_activity: [
    {
      type: "resume_built",
      at: "2026-05-30T12:00:00Z",
      title: "Resume built for Backend Engineer",
      subtitle: "Acme",
      meta: {},
    },
  ],
  ats_trend: [
    {
      date: "2026-05-28",
      score: 75,
      resume_id: "rec-1",
      jd_title: "Backend Engineer",
      jd_company: "Acme",
    },
    {
      date: "2026-05-30",
      score: 82,
      resume_id: "rec-1",
      jd_title: "Backend Engineer",
      jd_company: "Acme",
    },
  ],
}

const RESUMES_ALL_FIXTURE = {
  items: [
    {
      id: "rec-1",
      session_id: "sess-1",
      jd_title: "Backend Engineer",
      jd_company: "Acme",
      tags: ["python"],
      current_ats_score: 82,
      starting_ats_score: 75,
      ats_score_delta: 7,
      status: "draft",
      created_at: "2026-05-28T10:00:00Z",
      updated_at: "2026-05-30T12:00:00Z",
    },
    {
      id: "rec-2",
      session_id: "sess-2",
      jd_title: "Applied Role",
      jd_company: "Beta Corp",
      tags: [],
      current_ats_score: 70,
      starting_ats_score: 68,
      ats_score_delta: 2,
      status: "applied",
      created_at: "2026-05-25T10:00:00Z",
      updated_at: "2026-05-25T12:00:00Z",
    },
  ],
  total: 2,
  page: 1,
  page_size: 10,
}

const RESUMES_APPLIED_FIXTURE = {
  items: [RESUMES_ALL_FIXTURE.items[1]],
  total: 1,
  page: 1,
  page_size: 10,
}

const MOCK_ACCESS = "mock-access-token-dashboard"
const MOCK_USER = {
  id: "user-dashboard-e2e",
  email: "dashboard-e2e@example.com",
  display_name: "Test User",
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

async function mockDashboardApis(page: Page) {
  await page.route(`${API}/api/dashboard/summary`, (route: Route) =>
    route.fulfill({ json: SUMMARY_FIXTURE, status: 200 }),
  )
  await page.route(`${API}/api/resumes/bulk`, (route: Route) =>
    route.fulfill({ json: { ok: true, deleted: 2 }, status: 200 }),
  )
  await page.route(`${API}/api/resumes*`, (route: Route) => {
    if (route.request().method() !== "GET") {
      return route.continue()
    }
    const url = new URL(route.request().url())
    const statuses = url.searchParams.getAll("status")
    const body = statuses.includes("applied")
      ? RESUMES_APPLIED_FIXTURE
      : RESUMES_ALL_FIXTURE
    route.fulfill({ json: body, status: 200 })
  })
  await page.route(`${API}/api/subscriptions/current`, (route: Route) =>
    route.fulfill({
      json: { subscription: null, credit_balance: 5 },
      status: 200,
    }),
  )
}

test.describe("dashboard route guard", () => {
  test("GET /dashboard → redirects unauthenticated users to /auth", async ({ page }) => {
    await page.goto(`${BASE}/dashboard`)
    await page.waitForURL(/\/auth/)
    expect(page.url()).toContain("/auth")
  })
})

test.describe("dashboard page (mocked API)", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
    await mockDashboardApis(page)
    await login(page)
  })

  test("shows resume history section", async ({ page }) => {
    await expect(page.getByRole("heading", { name: /Resume history/i })).toBeVisible({
      timeout: 15000,
    })
    await expect(page.getByRole("heading", { name: "Backend Engineer" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Applied Role" })).toBeVisible()
    await expect(page.getByText("ATS 82")).toBeVisible()
  })

  test("filter by status=applied shows only applied resume", async ({ page }) => {
    await page.waitForSelector("select")
    await page.locator('select[aria-label="Status filters"]').selectOption(["applied"])
    await page.getByRole("button", { name: /Apply filters/i }).click()
    await expect(page.getByRole("heading", { name: "Applied Role" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Backend Engineer" })).not.toBeVisible()
  })

  test("bulk delete removes selected resumes from the list", async ({ page }) => {
    await expect(page.getByRole("heading", { name: "Backend Engineer" })).toBeVisible()
    await page.getByRole("checkbox", { name: "Select Backend Engineer" }).check()
    await page.getByRole("checkbox", { name: "Select Applied Role" }).check()
    await expect(page.getByText("2 selected")).toBeVisible()
    await page.getByRole("button", { name: "Delete" }).click()
    await expect(page.getByRole("heading", { name: "Backend Engineer" })).not.toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByRole("heading", { name: "Applied Role" })).not.toBeVisible()
    await expect(page.getByText("2 selected")).not.toBeVisible()
  })
})
