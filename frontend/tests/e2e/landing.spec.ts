/**
 * E2E tests for the public landing page (IMPLEMENTATION_PLAN §11d, Step 48).
 *
 * The landing page renders server-side from two public endpoints, so
 * page.route() cannot stub them — `tests/e2e/mock-api-server.mjs` serves
 * /api/billing/free-tier and /api/billing/prices instead. The price fixture
 * deliberately includes one synced plan (Pro, 1999 cents) and one unsynced
 * plan (Pro+, 0 cents) so the no-fabricated-price rule is enforced end to end.
 *
 * Paths are relative so the suite honours `PLAYWRIGHT_PORT`.
 *
 * Running locally (host :3000 is usually taken by Trust/Kia):
 *   E2E_MOCK_API=1 PLAYWRIGHT_PORT=3100 pnpm exec playwright test tests/e2e/landing.spec.ts
 * Without `E2E_MOCK_API` there is no price catalog, and the pricing
 * expectations below will fail rather than pass vacuously.
 */
import { test, expect } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/")
})

test.describe("hero", () => {
  test("leads with career discovery and keeps the ATS trust signals", async ({
    page,
  }) => {
    await expect(
      page.getByRole("heading", { level: 1, name: /not sure what to apply for/i }),
    ).toBeVisible()

    // ATS is the highest-intent search term and the no-fabrication promise is
    // the core differentiator — neither may be dropped from the hero.
    const badge = page.getByText(
      /ATS-optimized · Evidence-based · Never fabricates metrics/i,
    )
    await expect(badge).toBeVisible()
  })

  test("offers the no-account checkup alongside registration", async ({
    page,
  }) => {
    await expect(
      page.getByRole("link", { name: /start your career story/i }).first(),
    ).toHaveAttribute("href", "/auth?mode=register")

    await expect(
      page.getByRole("link", { name: /check a resume free/i }),
    ).toHaveAttribute("href", "/checkup")
  })

  test("advertises the real signup credit grant", async ({ page }) => {
    await expect(page.getByText(/6 credits on signup/i).first()).toBeVisible()
  })
})

test.describe("career discovery", () => {
  test("is a top-level section, not a footnote", async ({ page }) => {
    await expect(
      page.getByRole("heading", {
        level: 2,
        name: /you don.t have to know what to search for/i,
      }),
    ).toBeVisible()
  })

  test("labels its example data as illustrative", async ({ page }) => {
    // Required by the no-fabrication rule: sample fit scores must never read
    // as a claim about a real result.
    await expect(page.getByText(/illustrative example/i)).toBeVisible()
    await expect(page.getByText(/92% fit/)).toBeVisible()
  })
})

test.describe("journey", () => {
  test("renders all six stages in order", async ({ page }) => {
    const headings = page
      .getByRole("list", { name: "Job search stages" })
      .getByRole("heading", { level: 3 })

    await expect(headings).toHaveText([
      "Tell your story",
      "Discover where you fit",
      "Find opportunities",
      "Make every application fit",
      "Apply without the busywork",
      "Keep moving",
    ])
  })

  test("badges the partially gated stage instead of hiding the paywall", async ({
    page,
  }) => {
    // Scoped to the journey stage: the same badge intentionally appears in the
    // capability strip too.
    const jobs = page
      .getByRole("list", { name: "Job search stages" })
      .getByRole("listitem")
      .filter({ hasText: /find opportunities/i })
    await expect(jobs).toHaveCount(1)
    await expect(jobs.getByText("Free · expanded on paid")).toBeVisible()
    await expect(
      jobs.getByText(/expanded search and fit scoring need a paid plan/i),
    ).toBeVisible()
  })

  test("does not badge stages that are fully free", async ({ page }) => {
    const discover = page
      .getByRole("list", { name: "Job search stages" })
      .getByRole("listitem")
      .filter({ hasText: /discover where you fit/i })
    await expect(discover).toHaveCount(1)
    await expect(discover.getByText(/paid/i)).toHaveCount(0)
  })

  test("uses a contextual CTA per stage", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: /see my career options/i }),
    ).toHaveCount(1)
    await expect(
      page.getByRole("link", { name: /track my applications/i }),
    ).toHaveCount(1)
  })

  test("highlights one stage panel at a time while scrolling", async ({
    page,
  }) => {
    const panel = page.locator("#journey-panel")
    await expect(panel).toHaveAttribute("data-active-stage", "story")
    await expect(panel.getByRole("heading", { level: 3 })).toHaveText(
      /tell your story/i,
    )

    await page.locator('[data-journey-marker="jobs"]').scrollIntoViewIfNeeded()
    await expect(panel).toHaveAttribute("data-active-stage", "jobs")
    await expect(panel).toContainText(/find opportunities/i)
  })
})

test.describe("pricing", () => {
  test("shows the free tier and every public paid tier", async ({ page }) => {
    await expect(
      page.getByRole("heading", { level: 2, name: /start free, upgrade only/i }),
    ).toBeVisible()
    await expect(
      page.getByRole("heading", { level: 3, name: "Free", exact: true }),
    ).toBeVisible()
    for (const tier of ["Weekly", "Pro", "Pro+", "Premium"]) {
      await expect(
        page.getByRole("heading", { level: 3, name: tier, exact: true }),
      ).toBeVisible()
    }
    await expect(page.getByText("$9.99")).toBeVisible()
    await expect(page.getByText("$19.99")).toBeVisible()
  })

  test("never renders an unsynced plan as $0.00", async ({ page }) => {
    await expect(page.getByText("$0.00")).toHaveCount(0)
  })
})

test.describe("progressive disclosure", () => {
  test("keeps the detail collapsed until asked for", async ({ page }) => {
    const answer = page.getByText(
      /8-point QA checklist runs before every export/i,
    )
    await expect(answer).toBeHidden()

    await page
      .locator("details")
      .filter({ hasText: /how does FlintApply avoid inventing things/i })
      .locator("summary")
      .click()

    await expect(answer).toBeVisible()
  })
})

test.describe("closing CTA", () => {
  test("routes to registration", async ({ page }) => {
    await expect(
      page.getByRole("link", { name: /start my job search/i }),
    ).toHaveAttribute("href", "/auth?mode=register")
  })
})
