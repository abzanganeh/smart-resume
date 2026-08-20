/**
 * E2E onboarding tests (Playwright).
 *
 * Mocks backend auth + profile APIs so the inline master-resume upload
 * advances to job titles without leaving onboarding.
 */
import { test, expect, type Page, type Route } from "@playwright/test"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const MOCK_ACCESS = "mock-access-token-onboarding-e2e"

function incompleteOnboardingUser(overrides: Record<string, unknown> = {}) {
  return {
    id: "user-onboarding-e2e",
    email: "onboarding-e2e@example.com",
    display_name: "Onboarding E2E",
    tier: "free",
    credit_balance: 3,
    auth_provider: "email",
    email_verified_at: "2026-05-01T00:00:00Z",
    has_totp: false,
    closure_requested_at: null,
    suspended_at: null,
    onboarding_completed_at: null,
    onboarding_ai_choice: null,
    ...overrides,
  }
}

const MOCK_CHUNKS = [
  {
    id: "chunk-exp-1",
    section_type: "experience",
    content: "Built async pipelines at Acme for invoice processing in Python.",
    token_count: 12,
    metadata: {},
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  },
]

const MOCK_RESUME = {
  id: "resume-onboarding-e2e",
  raw_text: "Jane Doe resume fixture",
  parsed_sections: {},
  chunk_count: MOCK_CHUNKS.length,
  last_embedded_at: "2026-05-01T12:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T12:00:00Z",
}

async function mockOnboardingBackend(page: Page) {
  let user = incompleteOnboardingUser()

  await page.route(`${API}/api/auth/login`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        access_token: MOCK_ACCESS,
        token_type: "bearer",
        expires_in: 900,
        user,
      }),
    }),
  )

  await page.route(`${API}/api/auth/me`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(user),
    }),
  )

  await page.route(`${API}/api/auth/onboarding`, async (route: Route) => {
    if (route.request().method() !== "PATCH") return route.continue()
    const body = route.request().postDataJSON() as {
      ai_choice?: string
      complete?: boolean
    }
    user = {
      ...user,
      onboarding_ai_choice: body.ai_choice ?? user.onboarding_ai_choice,
      onboarding_completed_at: body.complete
        ? "2026-05-01T12:00:00Z"
        : user.onboarding_completed_at,
    }
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(user),
    })
  })

  await page.route(`${API}/api/profile/resume/chunks`, (route: Route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ chunks: [] }),
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/profile/resume`, async (route: Route) => {
    if (route.request().method() === "GET") {
      return route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: null,
          raw_text: "",
          parsed_sections: {},
          chunk_count: 0,
          last_embedded_at: null,
          created_at: null,
          updated_at: null,
        }),
      })
    }
    if (route.request().method() === "POST") {
      await new Promise((resolve) => setTimeout(resolve, 150))
      return route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({
          ...MOCK_RESUME,
          chunks: MOCK_CHUNKS,
        }),
      })
    }
    return route.continue()
  })

  await page.route(`${API}/api/jobs/preferences`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        preferred_titles: [],
        preferred_titles_confirmed: false,
      }),
    }),
  )
}

async function loginToOnboarding(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill("onboarding-e2e@example.com")
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/onboarding/, { timeout: 15_000 })
}

async function advanceToMasterStep(page: Page) {
  await expect(page.getByRole("heading", { name: /Welcome/i })).toBeVisible()
  await page.getByRole("button", { name: "Continue" }).click()
  await expect(page.getByRole("heading", { name: /How do you want to use AI/i })).toBeVisible()
  await page.getByRole("button", { name: "Continue" }).click()
  await expect(page.getByRole("heading", { name: /Build your master resume/i })).toBeVisible()
}

test.describe("onboarding inline master resume", () => {
  test("paste resume on master step advances to job titles without profile redirect", async ({
    page,
  }) => {
    await mockOnboardingBackend(page)
    await loginToOnboarding(page)
    await advanceToMasterStep(page)

    await expect(page.getByRole("button", { name: "Paste text" })).toBeVisible()
    await page.getByRole("button", { name: "Paste text" }).click()
    await page
      .getByPlaceholder("Paste your master resume text here…")
      .fill("Jane Doe\nSoftware Engineer\nPython, FastAPI")

    await page.getByRole("button", { name: "Save master resume" }).click()
    await expect(page.getByText("Chunking and embedding your resume…")).toBeVisible()

    await expect(page.getByRole("heading", { name: /Which roles should we search for/i })).toBeVisible({
      timeout: 10_000,
    })
    expect(page.url()).toContain("/onboarding")
    expect(page.url()).not.toContain("/profile")
  })
})
