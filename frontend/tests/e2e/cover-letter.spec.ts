/**
 * E2E: Phase 4 page → Generate cover letter → letter renders.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

const BASE = "http://localhost:3000";
const API = "http://localhost:8000";

const SESSION_ID = "e2e-cover-letter-session";
const MOCK_ACCESS = "mock-access-token-cover-letter";

const MOCK_USER = {
  id: "user-cover-letter-e2e",
  email: "cover-letter-e2e@example.com",
  display_name: "Cover Letter E2E",
  tier: "free",
  credit_balance: 3,
  auth_provider: "email",
  email_verified_at: "2026-05-01T00:00:00Z",
  has_totp: false,
  closure_requested_at: null,
  suspended_at: null,
};

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
};

const coverLetterOutput = {
  body_markdown: "Dear Hiring Manager,\n\nI am excited to apply.\n\nJane Doe",
  body_plain: "Dear Hiring Manager,\n\nI am excited to apply.\n\nJane Doe",
  word_count: 8,
  tone: "balanced",
  keywords_used: ["Python"],
};

const qaOutput = {
  checklist: [{ item: "Length", status: "pass", note: "OK" }],
  overall_status: "pass",
  user_action_required: [],
  ats_score: 80,
  blocking_issues: [],
  quick_wins: [],
};

function sessionPayload() {
  return {
    session_id: SESSION_ID,
    ok: true,
    resume_raw: "Jane Doe resume",
    phase1_complete: true,
    stale: { "3": null, "4": null },
    cover_letter: null,
    phases: {
      "1": { status: "done", output: { must_have_keywords: [], nice_to_have_keywords: [] } },
      "2": { status: "done", output: { keyword_coverage: {}, overall_score: 70, summary: "ok" } },
      "3": { status: "done", output: tailoredOutput },
      "4": { status: "done", output: qaOutput },
    },
  };
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
  );
}

async function login(page: Page) {
  await page.goto(`${BASE}/auth`);
  await page.getByPlaceholder("you@example.com").fill(MOCK_USER.email);
  await page.getByPlaceholder("••••••••••").fill("Str0ng!Password123");
  await page.locator("form").getByRole("button", { name: "Sign in" }).click();
  await page.waitForURL(/\/dashboard/, { timeout: 15_000 });
}

async function mockSessionAndCoverLetter(page: Page) {
  await page.route(`${API}/api/sessions/${SESSION_ID}`, async (route: Route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessionPayload()),
      });
      return;
    }
    await route.continue();
  });

  await page.route(`${API}/api/sessions/${SESSION_ID}/cover-letter`, async (route: Route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({ status: 404, contentType: "application/json", body: '{"detail":"No cover letter generated yet."}' });
      return;
    }
    if (route.request().method() === "POST") {
      const payload = JSON.stringify({ event: "done", output: coverLetterOutput });
      await route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: `data: ${payload}\n\ndata: {"event":"stream_end"}\n\n`,
      });
      return;
    }
    await route.continue();
  });
}

test("phase 4 page generate cover letter renders letter body", async ({ page }) => {
  await mockAuth(page);
  await mockSessionAndCoverLetter(page);
  await login(page);

  await page.goto(`${BASE}/session/${SESSION_ID}?step=export`);
  await expect(page.getByRole("heading", { name: "QA & Export" })).toBeVisible();

  await page.getByRole("button", { name: "Generate cover letter" }).click();
  await expect(page.getByRole("heading", { name: "Cover letter" })).toBeVisible();

  await page.getByRole("button", { name: "Generate", exact: true }).click();

  await expect(page.locator("textarea").filter({ hasText: "Dear Hiring Manager" })).toBeVisible({
    timeout: 15_000,
  });
  await expect(page.getByRole("link", { name: "PDF" })).toBeVisible();
});
