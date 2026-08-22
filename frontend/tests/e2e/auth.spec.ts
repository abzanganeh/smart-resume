/**
 * E2E auth tests (Playwright).
 *
 * Prerequisites:
 *   - Next.js dev server running on http://localhost:3000
 *   - Backend running on http://localhost:8000 (or mocked)
 *
 * Run: pnpm exec playwright test tests/e2e/auth.spec.ts
 */
import { test, expect } from "@playwright/test"

const PORT = process.env.PLAYWRIGHT_PORT ?? "3000"
const BASE = `http://localhost:${PORT}`

// ── Guard redirect ────────────────────────────────────────────────────────────

test.describe("unauthenticated route guard", () => {
  const protectedRoutes = [
    "/profile",
    "/billing",
    "/dashboard",
    "/session/new",
    "/jobs",
  ]

  for (const route of protectedRoutes) {
    test(`GET ${route} → redirects to /auth`, async ({ page }) => {
      await page.goto(`${BASE}${route}`)
      await page.waitForURL(/\/auth/)
      expect(page.url()).toContain("/auth")
      const callbackParam = new URL(page.url()).searchParams.get("callbackUrl")
      expect(callbackParam).toBeTruthy()
    })
  }
})

// ── Auth page renders ─────────────────────────────────────────────────────────

test.describe("/auth page", () => {
  test("renders Sign in and Register toggle tabs", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await expect(
      page.locator('button[type="button"]').filter({ hasText: "Sign in" }),
    ).toBeVisible()
    await expect(page.getByRole("button", { name: "Register" })).toBeVisible()
  })

  test("email sign-in fields are always visible", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await expect(page.getByPlaceholder("you@example.com")).toBeVisible()
    await expect(page.getByPlaceholder("••••••••••")).toBeVisible()
  })

  test("hides SSO buttons when OAuth uses placeholder credentials", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await expect(page.getByRole("button", { name: /Google/ })).toHaveCount(0)
    await expect(page.getByRole("button", { name: /GitHub/ })).toHaveCount(0)
  })

  test("switching to Register shows consent checkboxes", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await page.getByRole("button", { name: "Register" }).click()
    await expect(page.locator("form").getByText(/Terms of Service/)).toBeVisible()
    await expect(page.locator("form").getByText(/Privacy Policy/)).toBeVisible()
    await expect(page.getByText(/product updates/)).toBeVisible()
  })

  test("shows password strength meter while typing in register mode", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await page.getByRole("button", { name: "Register" }).click()
    const passwordInput = page.getByPlaceholder("••••••••••")
    await passwordInput.fill("abc")
    // Strength bar appears after first characters
    await expect(page.getByText(/Strength:/)).toBeVisible()
  })

  test("Sign in shows a forgot-password link to /auth/reset", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    const link = page.getByRole("link", { name: "Forgot your password?" })
    await expect(link).toBeVisible()
    await expect(link).toHaveAttribute("href", "/auth/reset")
  })

  test("forgot-password link carries the typed email", async ({ page }) => {
    await page.goto(`${BASE}/auth`)
    await page.getByPlaceholder("you@example.com").fill("reset-me@example.com")
    await expect(page.getByRole("link", { name: "Forgot your password?" })).toHaveAttribute(
      "href",
      "/auth/reset?email=reset-me%40example.com",
    )
  })
})

// ── Forgot / reset password ───────────────────────────────────────────────────

test.describe("/auth/reset", () => {
  test("request form sends a reset email and hides the address", async ({ page }) => {
    let forgotBody: string | null = null
    await page.route("**/api/auth/password/forgot", async (route) => {
      forgotBody = route.request().postData()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
    })

    await page.goto(`${BASE}/auth/reset?email=reset-me@example.com`)
    await expect(page.getByPlaceholder("you@example.com")).toHaveValue("reset-me@example.com")
    await page.getByRole("button", { name: "Send reset link" }).click()
    await expect(page.getByText(/If an account exists/i)).toBeVisible()
    expect(forgotBody).toContain("reset-me@example.com")
  })

  test("token form updates the password", async ({ page }) => {
    let resetPayload: string | null = null
    await page.route("**/api/auth/password/reset", async (route) => {
      resetPayload = route.request().postData()
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ ok: true }),
      })
    })

    await page.goto(`${BASE}/auth/reset?token=test-reset-token`)
    await expect(page.getByText("Choose a new password", { exact: true })).toBeVisible()
    const newPassword = "9X!verbatim-marsupial^tetrahedron"
    await page.locator("#reset-password").fill(newPassword)
    await page.locator("#reset-password-confirm").fill(newPassword)
    await page.getByRole("button", { name: "Update password" }).click()
    await expect(page.getByText(/Your password has been updated/)).toBeVisible()
    expect(resetPayload).toContain("test-reset-token")
    expect(resetPayload).toContain(newPassword)
  })

  test("expired reset token shows a request-again path", async ({ page }) => {
    await page.route("**/api/auth/password/reset", async (route) => {
      await route.fulfill({
        status: 400,
        contentType: "application/json",
        body: JSON.stringify({ detail: { code: "reset_token_expired" } }),
      })
    })

    await page.goto(`${BASE}/auth/reset?token=expired-token`)
    await page.locator("#reset-password").fill("9X!verbatim-marsupial^tetrahedron")
    await page.locator("#reset-password-confirm").fill("9X!verbatim-marsupial^tetrahedron")
    await page.getByRole("button", { name: "Update password" }).click()
    await expect(page.getByText(/reset link has expired/i)).toBeVisible()
    await expect(page.getByRole("link", { name: "Request a new reset link" })).toBeVisible()
  })
})

// ── Full register + first-login flow (integration — needs live backend) ───────

test.describe("register → email banner → login → onboarding", () => {
  // Skip unless PLAYWRIGHT_LIVE env is set (requires real backend)
  test.skip(
    process.env.PLAYWRIGHT_LIVE !== "true",
    "Set PLAYWRIGHT_LIVE=true and run against a real backend to enable this test",
  )

  const email = `test+e2e+${Date.now()}@example.com`
  const password = "Str0ng!Password123"

  test("full registration and first-login flow", async ({ page }) => {
    // 1. Go to /auth
    await page.goto(`${BASE}/auth`)

    // 2. Switch to Register
    await page.getByRole("button", { name: "Register" }).click()

    // 3. Fill form
    await page.getByPlaceholder("Your name").fill("E2E User")
    await page.getByPlaceholder("you@example.com").fill(email)
    await page.getByPlaceholder("••••••••••").fill(password)

    // 4. Accept checkboxes
    const checkboxes = page.getByRole("checkbox")
    await checkboxes.nth(0).check() // ToS
    await checkboxes.nth(1).check() // Privacy

    // 5. Submit
    await page.getByRole("button", { name: "Create account" }).click()

    // 6. Should show email verification banner
    await expect(page.getByText(/Check your email/i)).toBeVisible({ timeout: 10_000 })

    // 7. Navigate to /auth and login
    await page.goto(`${BASE}/auth`)
    await page.getByPlaceholder("you@example.com").fill(email)
    await page.getByPlaceholder("••••••••••").fill(password)
    await page.getByRole("button", { name: "Sign in" }).click()

    // 8. Should redirect to /onboarding on first login (onboarding not yet completed)
    await page.waitForURL(/\/onboarding/, { timeout: 10_000 })
    await expect(page.getByText(/Welcome/)).toBeVisible()
  })
})

// ── 2FA challenge step renders ────────────────────────────────────────────────

test.describe("2FA challenge step", () => {
  test("shows TOTP input when error param is 2fa_required", async ({ page }) => {
    const fakeToken = "eyJhbGciOiJIUzI1NiJ9.fakechallenge"
    await page.goto(
      `${BASE}/auth?error=${encodeURIComponent(`2fa_required:${fakeToken}:300`)}`,
    )
    await expect(page.getByText(/Two-factor authentication/)).toBeVisible()
    await expect(page.getByPlaceholder("000000")).toBeVisible()
    await expect(page.getByRole("button", { name: "Verify" })).toBeVisible()
  })

  test("toggling shows recovery code input", async ({ page }) => {
    const fakeToken = "eyJhbGciOiJIUzI1NiJ9.fakechallenge"
    await page.goto(
      `${BASE}/auth?error=${encodeURIComponent(`2fa_required:${fakeToken}:300`)}`,
    )
    await page.getByRole("button", { name: /recovery code instead/ }).click()
    await expect(page.getByPlaceholder("xxxx-xxxx")).toBeVisible()
  })
})
