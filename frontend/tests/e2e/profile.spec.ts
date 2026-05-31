/**
 * E2E profile tests (Playwright).
 *
 * Mocks backend auth + profile APIs so the upload → grouped chunks flow
 * runs without a live FastAPI server.
 *
 * Run: pnpm exec playwright test tests/e2e/profile.spec.ts
 */
import { test, expect, type Page, type Route } from "@playwright/test"
import { readFileSync } from "node:fs"
import { join } from "node:path"

const BASE = "http://localhost:3000"
const API = "http://localhost:8000"

const MOCK_USER = {
  id: "user-profile-e2e",
  email: "profile-e2e@example.com",
  display_name: "Profile E2E",
  tier: "free",
  credit_balance: 3,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
}

const MOCK_ACCESS = "mock-access-token-profile-e2e"

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
  {
    id: "chunk-exp-2",
    section_type: "experience",
    content: "Migrated legacy Django monolith to FastAPI microservices.",
    token_count: 11,
    metadata: {},
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  },
  {
    id: "chunk-skills-1",
    section_type: "skills",
    content: "Python, FastAPI, PostgreSQL, pgvector, Kubernetes, Redis",
    token_count: 10,
    metadata: {},
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  },
  {
    id: "chunk-edu-1",
    section_type: "education",
    content: "BS Computer Science, MIT (2017)",
    token_count: 8,
    metadata: {},
    created_at: "2026-05-01T00:00:00Z",
    updated_at: "2026-05-01T00:00:00Z",
  },
]

const MOCK_RESUME = {
  id: "resume-profile-e2e",
  raw_text: "John Doe resume fixture",
  parsed_sections: {},
  chunk_count: MOCK_CHUNKS.length,
  last_embedded_at: "2026-05-01T12:00:00Z",
  created_at: "2026-05-01T00:00:00Z",
  updated_at: "2026-05-01T12:00:00Z",
}

async function mockProfileBackend(page: Page) {
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
      await new Promise((resolve) => setTimeout(resolve, 250))
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

  await page.route(`${API}/api/resumes*`, (route: Route) =>
    route.fulfill({ status: 404, body: "not found" }),
  )
}

async function login(page: Page) {
  await page.goto(`${BASE}/auth`)
  await page.getByPlaceholder("you@example.com").fill(MOCK_USER.email)
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123")
  await page.locator("form").getByRole("button", { name: "Sign in" }).click()
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 })
}

test.describe("profile page", () => {
  test("drop TXT fixture → chunks appear grouped by section", async ({ page }) => {
    await mockProfileBackend(page)
    await login(page)

    await page.route(`${API}/api/profile/resume/chunks`, (route: Route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ chunks: MOCK_CHUNKS }),
      }),
    )

    await page.goto(`${BASE}/profile`)
    await expect(page.getByRole("heading", { name: /Master resume profile/i })).toBeVisible()

    const fixturePath = join(process.cwd(), "tests/fixtures/master-resume.txt")
    const fixture = readFileSync(fixturePath, "utf8")

    await page.locator("#profile-file-input").setInputFiles({
      name: "master-resume.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(fixture),
    })
    await expect(page.getByText("Chunking and embedding your resume…")).toBeVisible()

    await expect(page.getByRole("heading", { name: "Experience" })).toBeVisible({
      timeout: 10_000,
    })
    await expect(page.getByRole("heading", { name: "Skills" })).toBeVisible()
    await expect(page.getByRole("heading", { name: "Education" })).toBeVisible()

    const experienceSection = page.locator('[data-section="experience"]')
    await expect(experienceSection).toBeVisible()
    await expect(experienceSection.locator('[data-chunk-id="chunk-exp-1"]')).toBeVisible()
    await expect(experienceSection.locator('[data-chunk-id="chunk-exp-2"]')).toBeVisible()

    await expect(page.locator('[data-section="skills"]')).toBeVisible()
    await expect(page.locator('[data-section="education"]')).toBeVisible()
    await expect(page.getByText(/4 live chunks/)).toBeVisible()
  })
})

test.describe("profile route guard", () => {
  test("GET /profile → redirects unauthenticated users to /auth", async ({ page }) => {
    await page.goto(`${BASE}/profile`)
    await page.waitForURL(/\/auth/)
    expect(page.url()).toContain("/auth")
    expect(new URL(page.url()).searchParams.get("callbackUrl")).toBe("/profile")
  })
})
