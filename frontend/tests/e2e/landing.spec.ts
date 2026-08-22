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
import { suppressIntro } from "./helpers/intro"

test.beforeEach(async ({ page }) => {
  // Scrolling dismisses the intro, so the scroll-driven specs below pass by
  // accident today. Suppress it up front so they pass on purpose.
  await suppressIntro(page)
  await page.goto("/")
})

test("emits OWASP A02 security headers on the public landing route", async ({
  page,
}) => {
  const response = await page.goto("/")
  expect(response).not.toBeNull()
  const headers = response!.headers()
  expect(headers["content-security-policy"]).toContain(
    "frame-ancestors 'none'",
  )
  expect(headers["content-security-policy"]).toMatch(/'nonce-[-A-Za-z0-9+/=]+'/)
  expect(headers["content-security-policy"]).toContain("'strict-dynamic'")
  expect(headers["content-security-policy-report-only"]).toBeUndefined()
  expect(headers["x-content-type-options"]).toBe("nosniff")
  expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin")
  expect(headers["x-frame-options"]).toBe("DENY")
  expect(headers["permissions-policy"]).toContain("camera=()")
})

test.describe("hero", () => {
  test("leads with company watch and keeps the ATS trust signals", async ({
    page,
  }) => {
    await expect(
      page.getByRole("heading", { level: 1, name: /name the companies/i }),
    ).toBeVisible()

    const badge = page.getByText(
      /Company watch · Alerts in minutes · Never fabricates metrics/i,
    )
    await expect(badge).toBeVisible()

    // ATS is the highest-intent search term and the no-fabrication promise is
    // the core differentiator. The badge no longer carries ATS, so the
    // subheading has to, or the page loses the term entirely.
    await expect(page.getByText(/ATS-optimized resume/i).first()).toBeVisible()
  })

  test("states the free watch limit rather than implying unlimited", async ({
    page,
  }) => {
    // The hero promises "we'll tell you the minute they're hiring", but the
    // free tier is one company at 30 minutes (career_watch_companies=1).
    // The journey stage discloses the same limit, so scope to the hero.
    const hero = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { level: 1 }) })
    await expect(
      hero.getByText(/free plans watch one company/i),
    ).toBeVisible()
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

    // The rail prefixes each stage with its letter marker, so the heading text
    // is "A — Tell your story", not the bare title.
    await expect(headings).toHaveText([
      "A — Tell your story",
      "B — Discover where you fit",
      "C — Watch the companies you want",
      "D — Make every application fit",
      "E — Apply without the busywork",
      "F — Keep moving",
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
      .filter({ hasText: /watch the companies you want/i })
    await expect(jobs).toHaveCount(1)
    await expect(jobs.getByText("Free · expanded on paid")).toBeVisible()
    await expect(
      jobs.getByText(/add expanded search and fit scoring/i),
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

    // Pinned scrollytelling: use goToStage() geometry with instant scroll so
    // smooth-scroll inertia cannot overshoot to the track stage in headless CI.
    await page.evaluate(() => {
      const track = document
        .getElementById("journey-panel")
        ?.closest(".relative.mx-auto") as HTMLElement | null
      if (!track) return
      const rect = track.getBoundingClientRect()
      const index = 2 // jobs — story=0, discover=1, jobs=2
      const stepCount = 6
      const absoluteTop = rect.top + window.scrollY
      const travel = rect.height - window.innerHeight
      const share = (index + 0.5) / stepCount
      const target = travel <= 0 ? absoluteTop : absoluteTop + share * travel
      window.scrollTo({ top: Math.max(0, target), behavior: "instant" })
    })
    await expect(panel).toHaveAttribute("data-active-stage", "jobs", {
      timeout: 10_000,
    })
    await expect(panel).toContainText(/watch the companies you want/i)
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
