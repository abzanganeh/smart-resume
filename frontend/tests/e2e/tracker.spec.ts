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
    archived_at: null,
    created_at: "2026-05-28T10:00:00Z",
    updated_at: "2026-05-28T10:00:00Z",
  },
]

const detailState = {
  notes: "",
  contact_name: "",
  contact_email: "",
  job_url: "",
  status: "applied",
  rejection_reason: null as string | null,
  rejection_notes: null as string | null,
}

function buildApplicationDetail() {
  const base = APPLICATIONS_FIXTURE[0]
  return {
    ...base,
    status: detailState.status,
    notes: detailState.notes || null,
    contact_name: detailState.contact_name || null,
    contact_email: detailState.contact_email || null,
    job_url: detailState.job_url || null,
    rejection_reason: detailState.rejection_reason,
    rejection_notes: detailState.rejection_notes,
    status_history: [],
    interview_rounds: [],
    offer_detail: null,
    attachments: [],
    timeline: [],
    attachment_usage: {
      count: 0,
      total_bytes: 0,
      max_count: 5,
      max_file_bytes: 5242880,
      max_total_bytes: 10485760,
    },
  }
}

function buildApplicationSummary() {
  return {
    ...APPLICATIONS_FIXTURE[0],
    status: detailState.status,
  }
}

const FUNNEL_FIXTURE = {
  status_counts: {
    draft: 0,
    applied: 1,
    interviewing: 0,
    offer: 0,
    accepted: 0,
    rejected: 0,
    withdrawn: 0,
  },
  active_total: 1,
  archived_total: 0,
  total: 1,
  tracker_active_limit: 10,
}

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
  detailState.notes = ""
  detailState.contact_name = ""
  detailState.contact_email = ""
  detailState.job_url = ""
  detailState.status = "applied"
  detailState.rejection_reason = null
  detailState.rejection_notes = null

  await page.route(`${API}/api/resumes*`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 100 }),
    }),
  )

  // Funnel is polled by the tracker header alongside the row list; must be
  // mocked or the page hits the real backend and stalls.
  await page.route(`${API}/api/applications/funnel`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        ...FUNNEL_FIXTURE,
        status_counts: {
          ...FUNNEL_FIXTURE.status_counts,
          ...(patchedStatus
            ? {
                applied: patchedStatus === "applied" ? 1 : 0,
                interviewing: patchedStatus === "interviewing" ? 1 : 0,
                rejected: patchedStatus === "rejected" ? 1 : 0,
              }
            : {}),
        },
      }),
    }),
  )

  await page.route(/\/api\/applications(\?.*)?$/, (route: Route) => {
    if (route.request().method() === "GET") {
      const items = [buildApplicationSummary()]
      return route.fulfill({ json: items, status: 200 })
    }
    return route.continue()
  })

  await page.route(`${API}/api/applications/${APP_ID}/reminders`, (route: Route) =>
    route.fulfill({ json: [], status: 200 }),
  )

  await page.route(`${API}/api/applications/${APP_ID}`, (route: Route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({ json: buildApplicationDetail(), status: 200 })
    }
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON() as {
        status?: string
        notes?: string
        contact_name?: string
        contact_email?: string
        job_url?: string
        rejection_reason?: string
        rejection_notes?: string | null
      }
      if (body.status !== undefined) {
        detailState.status = body.status
        patchedStatus = body.status
      }
      if (body.notes !== undefined) detailState.notes = body.notes
      if (body.contact_name !== undefined) detailState.contact_name = body.contact_name
      if (body.contact_email !== undefined) detailState.contact_email = body.contact_email
      if (body.job_url !== undefined) detailState.job_url = body.job_url
      if (body.rejection_reason !== undefined) {
        detailState.rejection_reason = body.rejection_reason
      }
      if (body.rejection_notes !== undefined) {
        detailState.rejection_notes = body.rejection_notes
      }
      return route.fulfill({ json: buildApplicationSummary(), status: 200 })
    }
    return route.continue()
  })
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

test.describe("tracker detail (mocked API)", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuth(page)
    await mockTrackerApis(page)
    await login(page)
  })

  test("loads application detail from kanban link", async ({ page }) => {
    await page.goto(`${BASE}/tracker`)
    await expect(page.getByRole("heading", { name: /Application tracker/i })).toBeVisible({
      timeout: 15_000,
    })

    const detailPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/applications/${APP_ID}`) && req.method() === "GET",
    )
    const remindersPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/applications/${APP_ID}/reminders`) &&
        req.method() === "GET",
    )

    await page.getByRole("link", { name: "Software Engineer" }).click()
    await page.waitForURL(new RegExp(`/tracker/${APP_ID}`), { timeout: 15_000 })
    await detailPromise
    await remindersPromise

    await expect(page.getByRole("heading", { name: "Software Engineer" })).toBeVisible()
    await expect(page.getByText("Beta Corp")).toBeVisible()
    await expect(page.getByRole("heading", { name: "Timeline" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Contact & notes" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Reminders" })).toBeVisible()
    await expect(page.getByRole("link", { name: "Back to pipeline" })).toBeVisible()
  })

  test("save contact details PATCHes notes", async ({ page }) => {
    await page.goto(`${BASE}/tracker/${APP_ID}`)
    await expect(page.getByRole("heading", { name: "Software Engineer" })).toBeVisible({
      timeout: 15_000,
    })

    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/applications/${APP_ID}`) &&
        req.method() === "PATCH" &&
        (req.postDataJSON() as { notes?: string }).notes ===
          "Follow up with recruiter next week",
    )

    await page.getByPlaceholder("Notes").fill("Follow up with recruiter next week")
    await page.getByRole("button", { name: "Save contact details" }).click()
    await patchPromise

    await expect(page.getByPlaceholder("Notes")).toHaveValue(
      "Follow up with recruiter next week",
    )
  })

  test("rejection form PATCHes status to rejected", async ({ page }) => {
    await page.goto(`${BASE}/tracker/${APP_ID}`)
    await expect(page.getByRole("heading", { name: "Software Engineer" })).toBeVisible({
      timeout: 15_000,
    })

    const patchPromise = page.waitForRequest(
      (req) =>
        req.url().includes(`/api/applications/${APP_ID}`) &&
        req.method() === "PATCH" &&
        (req.postDataJSON() as { status?: string }).status === "rejected",
    )

    await page
      .locator("form")
      .filter({ has: page.getByRole("button", { name: "Update rejection / withdrawal" }) })
      .locator("select")
      .first()
      .selectOption("rejected")
    await page
      .locator("form")
      .filter({ has: page.getByRole("button", { name: "Update rejection / withdrawal" }) })
      .locator("select")
      .nth(1)
      .selectOption("ghosted")
    await page.getByPlaceholder("Optional notes").fill("No response after 3 weeks")
    await page.getByRole("button", { name: "Update rejection / withdrawal" }).click()
    const patchReq = await patchPromise
    const body = patchReq.postDataJSON() as {
      status: string
      rejection_reason: string
      rejection_notes: string
    }
    expect(body.status).toBe("rejected")
    expect(body.rejection_reason).toBe("ghosted")
    expect(body.rejection_notes).toBe("No response after 3 weeks")

    await expect(page.getByText("rejected", { exact: true })).toBeVisible()
  })
})
