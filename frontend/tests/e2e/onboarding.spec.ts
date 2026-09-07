/**
 * E2E onboarding tests (Playwright).
 *
 * Onboarding is intro-only — setup happens from profile / jobs/setup after finish.
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
}

async function loginToOnboarding(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill("onboarding-e2e@example.com")
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/onboarding/, { timeout: 15_000 })
}

test.describe("onboarding intro wizard", () => {
  test("walks through all five intro steps with back navigation on job titles", async ({
    page,
  }) => {
    await mockOnboardingBackend(page)
    await loginToOnboarding(page)

    await expect(page.getByRole("heading", { name: /Welcome/i })).toBeVisible()
    await page.getByRole("button", { name: "Continue" }).click()

    await expect(page.getByRole("heading", { name: /How do you want to use AI/i })).toBeVisible()
    await page.getByRole("button", { name: "Continue" }).click()

    await expect(page.getByRole("heading", { name: /Build your master resume/i })).toBeVisible()
    await expect(page.getByText(/upload a file, paste text, or speak/i)).toBeVisible()
    await page.getByRole("button", { name: "Continue" }).click()

    await expect(page.getByRole("heading", { name: /Which roles should we search for/i })).toBeVisible()
    await expect(page.getByRole("button", { name: "Back" })).toBeVisible()
    await page.getByRole("button", { name: "Continue" }).click()

    await expect(page.getByRole("heading", { name: /You're all set/i })).toBeVisible()
    await expect(page.getByRole("link", { name: /Add your master resume/i })).toBeVisible()
    await expect(page.getByRole("link", { name: /Choose job titles to search/i })).toBeVisible()
    expect(page.url()).toContain("/onboarding")
  })
})
