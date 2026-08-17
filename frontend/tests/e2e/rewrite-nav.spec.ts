/**
 * E2E: Phase 2 audit edit → Phase 3 stale banner → Re-run clears banner.
 *
 * Mocks the backend session API so the flow runs without a live FastAPI server.
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const SESSION_ID = "e2e-stale-nav-session"
const MOCK_ACCESS = "mock-access-token-rewrite-nav"

const MOCK_USER = {
  id: "user-rewrite-nav-e2e",
  email: "rewrite-nav-e2e@example.com",
  display_name: "Rewrite Nav E2E",
  tier: "free",
  credit_balance: 3,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

const auditOutput = {
  keyword_coverage: { present: ["Python"], missing_must_have: [], missing_nice_to_have: [] },
  bullet_issues: [],
  cliches_found: [],
  irrelevant_sections: [],
  page_estimate: "1 page",
  page_limit_exceeded: false,
  contact_issues: [],
  overall_score: 72,
  summary: "Initial audit summary.",
}

const tailoredOutput = {
  contact: { name: "Jane Doe" },
  summary: "Tailored summary.",
  skills: ["Python"],
  experience: [
    {
      title: "Engineer",
      company: "Acme",
      dates: "2020–2024",
      bullets: ["Built APIs"],
      removed_bullets: [],
      keywords_injected: [],
    },
  ],
  projects: [],
  education: [],
  certifications: [],
  rewrite_notes: [],
  metrics_needed: [],
}

function sessionPayload(stale: Record<string, string | null>) {
  return {
    session_id: SESSION_ID,
    ok: true,
    resume_raw: "Jane Doe resume",
    phase1_complete: true,
    stale,
    phases: {
      "1": {
        status: "done",
        output: {
          must_have_keywords: [{ term: "Python", source_sentence: "", category: "skill", tier: "must_have", reason: "", present_in_resume: true }],
          nice_to_have_keywords: [],
          action_verbs: [],
          seniority_signals: [],
          boolean_search_terms: [],
          role_context: { career_level: "mid", needs_ml_framing: false, primary_domain: "software" },
        },
      },
      "2": { status: "done", output: auditOutput },
      "3": { status: "done", output: tailoredOutput },
      "4": { status: "pending", output: null },
    },
  }
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

async function mockSessionBackend(page: Page, getStale: () => Record<string, string | null>) {
  await page.route(`${API}/api/sessions/${SESSION_ID}`, async (route: Route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessionPayload(getStale())),
      })
      return
    }
    await route.continue()
  })

  await page.route(`${API}/api/sessions/${SESSION_ID}/audit`, async (route: Route) => {
    if (route.request().method() === "PATCH") {
      staleState["3"] = new Date().toISOString()
      staleState["4"] = new Date().toISOString()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: true,
          stale: { ...staleState },
        }),
      })
      return
    }
    await route.continue()
  })

  await page.route(`${API}/api/sessions/${SESSION_ID}/phases/3/run`, async (route: Route) => {
    if (route.request().method() === "POST") {
      staleState["3"] = null
      staleState["4"] = null
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "phase3-mock",
          stream_url: `${API}/api/sessions/${SESSION_ID}/phases/3/events`,
        }),
      })
      return
    }
    await route.continue()
  })

  await page.route(`${API}/api/sessions/${SESSION_ID}/phases/3/events`, async (route: Route) => {
    const payload = JSON.stringify({
      event: "done",
      phase: 3,
      output: tailoredOutput,
    })
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `data: ${payload}\n\ndata: {"event":"stream_end"}\n\n`,
    })
  })
}

const staleState: Record<string, string | null> = { "3": null, "4": null }

test("audit edit shows stale banner on rewrite tab; re-run clears it", async ({ page }) => {
  staleState["3"] = null
  staleState["4"] = null
  await mockAuth(page)
  await mockSessionBackend(page, () => staleState)
  await login(page)

  await page.goto(`${BASE}/session/${SESSION_ID}?step=analysis`)
  await expect(page.getByRole("heading", { name: "Analysis" })).toBeVisible()

  await page.getByRole("button", { name: "Edit" }).click()
  await page.locator("textarea").first().fill("Updated audit summary after manual edit.")
  await page.getByRole("button", { name: "Save audit edit" }).click()

  await page.getByRole("button", { name: "Tailored Rewrite" }).click()
  await expect(page.getByText("Your audit changed. Re-run Phase 3 to apply updates.")).toBeVisible()

  await page.getByRole("button", { name: "Re-run" }).click()
  await expect(page.getByText("Your audit changed. Re-run Phase 3 to apply updates.")).toBeHidden({
    timeout: 15_000,
  })
})

test("phase tabs are clickable after phase 1 without auto-running rewrite", async ({ page }) => {
  staleState["3"] = null
  staleState["4"] = null

  let rewriteRunRequested = false
  await mockAuth(page)
  await mockSessionBackend(page, () => staleState)
  await login(page)

  await page.route(`${API}/api/sessions/${SESSION_ID}/phases/3/run`, async (route: Route) => {
    rewriteRunRequested = true
    await route.fulfill({ status: 202, body: JSON.stringify({ job_id: "x", stream_url: "/events" }) })
  })

  await page.goto(`${BASE}/session/${SESSION_ID}?step=analysis`)
  await page.getByRole("button", { name: "Tailored Rewrite" }).click()
  await expect(page.getByRole("heading", { name: "Tailored Rewrite" })).toBeVisible()
  await expect(page.getByText("Tailored summary.")).toBeVisible()
  expect(rewriteRunRequested).toBe(false)
})
