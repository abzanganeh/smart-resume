/**
 * E2E: search → results appear → Tailor Resume navigates to /session/new with JD prefilled.
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const MOCK_ACCESS = "mock-access-token-jobs"
const MOCK_JOB_ID = "11111111-1111-1111-1111-111111111111"

const MOCK_USER = {
  id: "user-jobs-e2e",
  email: "jobs-e2e@example.com",
  display_name: "Jobs E2E",
  tier: "paid",
  credit_balance: 0,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

const MOCK_JOB = {
  id: MOCK_JOB_ID,
  title: "Senior Python Engineer",
  company: "Acme Labs",
  location: "Remote",
  remote: true,
  salary_min_usd: 140000,
  salary_max_usd: 180000,
  employment_type: "full-time",
  posted_date: "2026-05-20T00:00:00Z",
  description:
    "We are hiring a Senior Python Engineer to build APIs with FastAPI and PostgreSQL.",
  apply_url: "https://example.com/jobs/python",
  sources: ["hirebase"],
  score: null,
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

async function mockSubscription(page: Page) {
  await page.route(`${API}/api/subscriptions/current`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        subscription: {
          id: "sub-jobs-e2e",
          plan: "monthly",
          billing_cycle: "recurring",
          status: "active",
          trial_ends_at: null,
          period_start: "2026-05-01T00:00:00Z",
          period_end: "2026-06-01T00:00:00Z",
          resumes_used: 0,
          resumes_limit: 150,
          searches_used: 0,
          searches_limit: 300,
          cancel_at_period_end: false,
          paused_at: null,
          pause_resumes_at: null,
        },
        credit_balance: 0,
      }),
    }),
  )
}

async function mockJobsApi(page: Page) {
  await page.route(`${API}/api/jobs/saved`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([]),
    }),
  )

  await page.route(`${API}/api/jobs/search`, async (route: Route) => {
    if (route.request().method() !== "POST") {
      await route.continue()
      return
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        jobs: [MOCK_JOB],
        total: 1,
        page: 1,
        page_size: 20,
        results_may_be_stale: false,
        message: null,
      }),
    })
  })

  await page.route(`${API}/api/jobs/${MOCK_JOB_ID}`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_JOB),
    }),
  )

  await page.route(`${API}/api/sessions`, (route: Route) => {
    if (route.request().method() === "POST") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ session_id: "session-jobs-e2e" }),
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/sessions/session-jobs-e2e`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        session_id: "session-jobs-e2e",
        ok: true,
        resume_raw: "",
        phases: {},
        stale: {},
        phase1_complete: false,
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

test("search results tailor resume navigates with jd prefilled", async ({ page }) => {
  await mockAuth(page)
  await mockSubscription(page)
  await mockJobsApi(page)
  await login(page)

  await page.goto(`${BASE}/jobs`)
  await expect(page.getByRole("heading", { name: "Search jobs" })).toBeVisible()

  await page.getByTestId("jobs-search-role").fill("Python engineer")
  await page.getByTestId("jobs-search-submit").click()

  await expect(page.getByText("Senior Python Engineer")).toBeVisible({ timeout: 10_000 })
  await expect(page.getByText("Acme Labs")).toBeVisible()

  await page.getByTestId(`tailor-resume-${MOCK_JOB_ID}`).click()

  await page.waitForURL(/\/session\/new/, { timeout: 15_000 })
  expect(page.url()).toContain(`jd_id=${MOCK_JOB_ID}`)

  await expect(
    page.getByPlaceholder("Paste the full job description here…"),
  ).toHaveValue(/Senior Python Engineer/, { timeout: 10_000 })
})
