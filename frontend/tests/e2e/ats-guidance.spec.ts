/**
 * E2E: Phase 4 QA → ATS Guidance panel shows score + blocking issues.
 */
import { test, expect, type Page, type Route } from "@playwright/test";

import { ATS_GUIDANCE_FIXTURE } from "../components/ATSGuidancePanel.test";

const BASE = "http://localhost:3000";
const API = "http://localhost:8000";

const SESSION_ID = "e2e-ats-guidance-session";
const MOCK_ACCESS = "mock-access-token-ats-guidance";

const MOCK_USER = {
  id: "user-ats-guidance-e2e",
  email: "ats-guidance-e2e@example.com",
  display_name: "ATS Guidance E2E",
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

function sessionPayload(qaOutput: typeof ATS_GUIDANCE_FIXTURE | null) {
  return {
    session_id: SESSION_ID,
    ok: true,
    resume_raw: "Jane Doe resume",
    phase1_complete: true,
    stale: { "3": null, "4": null },
    phases: {
      "1": {
        status: "done",
        output: {
          must_have_keywords: [
            {
              term: "Python",
              source_sentence: "",
              category: "skill",
              tier: "must_have",
              reason: "",
              present_in_resume: true,
            },
          ],
          nice_to_have_keywords: [],
          action_verbs: [],
          seniority_signals: [],
          boolean_search_terms: [],
          role_context: { career_level: "mid", needs_ml_framing: false, primary_domain: "software" },
        },
      },
      "2": {
        status: "done",
        output: {
          keyword_coverage: { present: ["Python"], missing_must_have: [], missing_nice_to_have: [] },
          bullet_issues: [],
          cliches_found: [],
          irrelevant_sections: [],
          page_estimate: "1 page",
          page_limit_exceeded: false,
          contact_issues: [],
          overall_score: 72,
          summary: "Audit summary.",
        },
      },
      "3": { status: "done", output: tailoredOutput },
      "4": qaOutput ? { status: "done", output: qaOutput } : { status: "pending", output: null },
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

async function mockSessionWithPhase4(page: Page, qaOutput: typeof ATS_GUIDANCE_FIXTURE | null) {
  await page.route(`${API}/api/sessions/${SESSION_ID}`, async (route: Route) => {
    if (route.request().method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(sessionPayload(qaOutput)),
      });
      return;
    }
    await route.continue();
  });

  await page.route(`${API}/api/sessions/${SESSION_ID}/phases/4/run`, async (route: Route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: JSON.stringify({
          job_id: "phase4-mock",
          stream_url: `${API}/api/sessions/${SESSION_ID}/phases/4/events`,
        }),
      });
      return;
    }
    await route.continue();
  });

  await page.route(`${API}/api/sessions/${SESSION_ID}/phases/4/events`, async (route: Route) => {
    const payload = JSON.stringify({
      event: "done",
      phase: 4,
      output: ATS_GUIDANCE_FIXTURE,
    });
    await route.fulfill({
      status: 200,
      contentType: "text/event-stream",
      body: `data: ${payload}\n\ndata: {"event":"stream_end"}\n\n`,
    });
  });
}

test("phase 4 run shows ATS score and blocking issues", async ({ page }) => {
  await mockAuth(page);
  await mockSessionWithPhase4(page, null);
  await login(page);

  await page.goto(`${BASE}/session/${SESSION_ID}?step=export`);
  await expect(page.getByRole("heading", { name: "QA & Export" })).toBeVisible();

  await page.getByRole("button", { name: "Run QA checklist" }).click();

  await expect(page.getByText("74")).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Up to 91 achievable/)).toBeVisible();
  await expect(page.getByText("Blocking issues (3)")).toBeVisible();
  await expect(page.getByText("Missing Kubernetes in Skills.").first()).toBeVisible();
  await expect(page.getByRole("button", { name: "Apply" })).toBeVisible();
});

test("cached phase 4 output renders ATS panel without re-run", async ({ page }) => {
  await mockAuth(page);
  await mockSessionWithPhase4(page, ATS_GUIDANCE_FIXTURE);
  await login(page);

  await page.goto(`${BASE}/session/${SESSION_ID}?step=export`);

  await expect(page.getByText(/Up to 91 achievable/)).toBeVisible();
  await expect(page.getByText("Quick wins")).toBeVisible();
  await expect(page.getByText("Blocking issues (3)")).toBeVisible();
});
