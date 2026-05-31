/**
 * E2E: paste JD → analyze → fit score displayed.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

const BASE = "http://localhost:3000";
const API = "http://localhost:8000";

const MOCK_ACCESS = "mock-access-token-fit";

const MOCK_USER = {
  id: "user-fit-e2e",
  email: "fit-e2e@example.com",
  display_name: "Fit E2E",
  tier: "paid",
  credit_balance: 0,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
};

const MOCK_FIT_OUTPUT = {
  overall_fit_score: 82,
  fit_label: "strong",
  section_fits: [
    {
      section_type: "experience",
      match_score: 88,
      matched_items: ["Python APIs"],
      missing_items: ["Kubernetes"],
    },
  ],
  key_gaps: ["Kubernetes at scale"],
  key_strengths: ["Python backend experience"],
  recommendation: "Strong match — tailor your resume to emphasize cloud skills.",
  should_apply: true,
  suggested_master_resume_edits: ["Quantify API throughput metrics"],
};

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
  );
}

async function mockSubscription(page: Page) {
  await page.route(`${API}/api/subscriptions/current`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        subscription: {
          id: "sub-fit-e2e",
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
  );
}

async function mockFitAnalyze(page: Page) {
  await page.route(`${API}/api/fit/analyze`, async (route: Route) => {
    if (route.request().method() !== "POST") {
      await route.continue();
      return;
    }
    const payload = JSON.stringify({
      event: "done",
      analysis_id: "fit-analysis-e2e",
      output: MOCK_FIT_OUTPUT,
    });
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `data: ${payload}\n\ndata: {"event":"stream_end"}\n\n`,
    });
  });

  await page.route(`${API}/api/fit/history*`, (route: Route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ items: [], total: 0, page: 1, page_size: 20 }),
    }),
  );
}

async function login(page: Page) {
  await page.goto(`${BASE}/auth`);
  await page.getByPlaceholder("you@example.com").fill(MOCK_USER.email);
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123");
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
}

test("paste JD analyze fit score displayed", async ({ page }) => {
  await mockAuth(page);
  await mockSubscription(page);
  await mockFitAnalyze(page);
  await login(page);

  await page.goto(`${BASE}/fit`);
  await expect(page.getByRole("heading", { name: "Job fit analysis" })).toBeVisible();

  await page.getByRole("button", { name: "Paste JD" }).click();
  await page.getByPlaceholder("Paste the full job description").fill(
    "Backend Engineer with Python, FastAPI, and PostgreSQL.",
  );
  await page.getByRole("button", { name: "Analyze fit" }).click();

  await expect(page.getByText("82")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText("Strong fit")).toBeVisible();
  await expect(page.getByText("Strong match — tailor your resume")).toBeVisible();
});
