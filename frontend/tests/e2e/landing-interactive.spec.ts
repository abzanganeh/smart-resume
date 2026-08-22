/**
 * E2E for the landing page's pointer interaction and crawler assets
 * (IMPLEMENTATION_PLAN §11e, Step 53).
 *
 * The interaction is presentational, so these tests are written the way the
 * feature is specified: the content must be complete without a pointer, the
 * pointer must add emphasis on top, and an explicit reduced-motion request must
 * remove the movement without removing anything else.
 *
 * Running locally (host :3000 is usually taken by Trust/Kia):
 *   E2E_MOCK_API=1 PLAYWRIGHT_PORT=3100 pnpm exec playwright test tests/e2e/landing-interactive.spec.ts
 */
import { test, expect, type Locator, type Page } from "@playwright/test"
import { suppressIntro } from "./helpers/intro"

const CAPABILITY_COUNT = 8

// Runs before every describe-level hook in this file. The intro overlay covers
// the viewport and eats pointer events, which breaks every `page.mouse.move`
// below.
test.beforeEach(async ({ page }) => {
  await suppressIntro(page)
})

/**
 * Move the pointer onto a capability card deterministically.
 *
 * Not `locator.hover()`: that scrolls as part of the same action, and the
 * pointer can settle at coordinates measured before the scroll finished with no
 * subsequent move to correct it. The result was an intermittent failure to
 * register the hover at all. Scrolling first, then measuring, then moving
 * removes the race.
 */
async function hoverCapability(page: Page, id: string): Promise<Locator> {
  await page.locator("[data-spotlight-panel]").scrollIntoViewIfNeeded()
  const card = page.locator(`[data-capability="${id}"]`)
  const box = await card.boundingBox()
  if (!box) throw new Error(`capability card ${id} has no bounding box`)
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  return card
}

/** Park the pointer in the viewport corner, well clear of any panel. */
async function movePointerAway(page: Page): Promise<void> {
  await page.mouse.move(2, 2)
}

test.describe("capability spotlight", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/")
  })

  test("renders every capability without any pointer interaction", async ({
    page,
  }) => {
    // The whole point of keeping the pointer layer presentational: this content
    // has to be there for crawlers, for assistive technology, and before
    // hydration. If a future change hides a blurb behind hover, this fails.
    const cards = page.locator("[data-capability]")
    await expect(cards).toHaveCount(CAPABILITY_COUNT)

    for (let index = 0; index < CAPABILITY_COUNT; index += 1) {
      await expect(cards.nth(index)).toBeVisible()
    }

    await expect(
      page.getByRole("heading", { level: 3, name: "ATS Optimization" }),
    ).toBeVisible()
    await expect(
      page.getByText(/keyword extraction, gap audit, and a scored quality check/i),
    ).toBeVisible()
  })

  test("emphasises no card until the pointer arrives", async ({ page }) => {
    const active = page.locator('[data-capability][data-active="true"]')
    await expect(active).toHaveCount(0)
  })

  test("emphasises the card under the cursor", async ({ page }) => {
    const target = await hoverCapability(page, "ats")

    await expect(target).toHaveAttribute("data-active", "true")
    // Exactly one card is emphasised, so the effect cannot smear across the grid.
    await expect(page.locator('[data-capability][data-active="true"]')).toHaveCount(
      1,
    )
  })

  test("moves the emphasis with the cursor", async ({ page }) => {
    const first = await hoverCapability(page, "story")
    await expect(first).toHaveAttribute("data-active", "true")

    const later = await hoverCapability(page, "tracker")
    await expect(later).toHaveAttribute("data-active", "true")
    await expect(first).toHaveAttribute("data-active", "false")
  })

  test("drops the emphasis when the pointer leaves the panel", async ({
    page,
  }) => {
    const target = await hoverCapability(page, "ats")
    await expect(target).toHaveAttribute("data-active", "true")

    await movePointerAway(page)
    await expect(
      page.locator('[data-capability][data-active="true"]'),
    ).toHaveCount(0)
  })

  test("does not re-emphasise a card after a fast exit off the panel", async ({
    page,
  }) => {
    const panel = page.locator("[data-spotlight-panel]")
    await panel.scrollIntoViewIfNeeded()
    const box = await panel.boundingBox()
    if (!box) throw new Error("spotlight panel has no bounding box")

    // Continuous motion off the edge can schedule a frame after pointerleave.
    await page.mouse.move(box.x + box.width * 0.5, box.y + box.height * 0.5, {
      steps: 8,
    })
    await page.mouse.move(box.x + box.width + 40, box.y + box.height * 0.5, {
      steps: 12,
    })

    await expect(
      page.locator('[data-capability][data-active="true"]'),
    ).toHaveCount(0)
  })

  test("applies a transform to the emphasised card", async ({ page }) => {
    const target = await hoverCapability(page, "ats")
    await expect(target).toHaveAttribute("data-active", "true")

    // Polled rather than read once: `transform` is transitioned over 160ms, so
    // a single read straight after the hover catches the identity matrix at the
    // start of the interpolation rather than the settled value.
    await expect
      .poll(() =>
        target.evaluate((node) => getComputedStyle(node).transform),
      )
      .not.toBe("none")
  })

  test("reveals the spotlight gradient while the pointer is inside", async ({
    page,
  }) => {
    // The gradient's visibility comes from a CSS :hover rule, which synthetic
    // events cannot trigger — only real pointer input does. Asserting it here
    // means a refactor that drops the hover rule cannot pass silently.
    const overlay = page.locator(".sr-spotlight")
    expect(await overlay.evaluate((node) => getComputedStyle(node).opacity)).toBe(
      "0",
    )

    await hoverCapability(page, "ats")

    await expect
      .poll(() => overlay.evaluate((node) => getComputedStyle(node).opacity))
      .toBe("1")
  })
})

test.describe("capability spotlight with reduced motion", () => {
  test("stops moving without hiding anything", async ({ page }) => {
    // `test.use({ reducedMotion })` does not take effect here — matchMedia still
    // reported no-preference inside the page — so emulate explicitly, and do it
    // before navigating so the mount-time media query sees it.
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/")

    // Content is untouched by the preference.
    await expect(page.locator("[data-capability]")).toHaveCount(CAPABILITY_COUNT)
    await expect(
      page.getByRole("heading", { level: 3, name: "ATS Optimization" }),
    ).toBeVisible()

    const target = await hoverCapability(page, "ats")

    // Two independent guarantees: the component refuses to mark a card active,
    // and the stylesheet neutralises the transform even if it did.
    await expect(target).toHaveAttribute("data-active", "false")
    const transform = await target.evaluate(
      (node) => getComputedStyle(node).transform,
    )
    expect(transform).toBe("none")
  })

  test("keeps the scan demo readable without sweeping", async ({ page }) => {
    await page.emulateMedia({ reducedMotion: "reduce" })
    await page.goto("/")

    await expect(page.locator("[data-keyword]")).toHaveCount(7)
    await expect(
      page.locator('[data-keyword][data-status="missing"]').first(),
    ).toBeVisible()

    // Nothing is dimmed, because the sweep never runs.
    const surface = page.locator("[data-scan-surface]")
    await surface.scrollIntoViewIfNeeded()
    const box = await surface.boundingBox()
    if (!box) throw new Error("scan surface has no box")
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)

    const opacities = await page
      .locator("[data-keyword]")
      .evaluateAll((nodes) =>
        nodes.map((node) => getComputedStyle(node).opacity),
      )
    expect(opacities.every((value) => value === "1")).toBe(true)
  })
})

test.describe("keyword scan demo", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/")
  })

  test("shows every keyword and its verdict before any interaction", async ({
    page,
  }) => {
    const keywords = page.locator("[data-keyword]")
    await expect(keywords).toHaveCount(7)

    // Both outcomes are present: a demo where everything matches teaches
    // nothing about the gap audit, which is the capability being shown.
    await expect(page.locator('[data-keyword][data-status="matched"]')).not.toHaveCount(
      0,
    )
    await expect(page.locator('[data-keyword][data-status="missing"]')).not.toHaveCount(
      0,
    )
  })

  test("labels the sample data as sample data", async ({ page }) => {
    // Required by the no-fabrication rule. Worded differently from the career
    // discovery caption so neither assertion depends on the other's phrasing.
    await expect(
      page.getByText(/sample resume and job description/i),
    ).toBeVisible()
  })

  test("reports the coverage count that matches the rendered verdicts", async ({
    page,
  }) => {
    const matched = await page
      .locator('[data-keyword][data-status="matched"]')
      .count()
    const total = await page.locator("[data-keyword]").count()

    await expect(
      page.getByText(`${matched} of ${total} must-haves covered`),
    ).toBeVisible()
  })

  test("sweeps a visible line and dims only what it has not reached", async ({
    page,
  }) => {
    const sweep = page.locator(".sr-scan-sweep")
    const surface = page.locator("[data-scan-surface]")
    // boundingBox() is viewport-relative, so the panel has to be scrolled into
    // view before mouse.move can land on it. Without this the pointer goes to a
    // coordinate below the fold and hovers nothing.
    await surface.scrollIntoViewIfNeeded()
    const box = await surface.boundingBox()
    if (!box) throw new Error("scan surface has no box")

    // At rest the sweep is hidden and nothing is dimmed.
    expect(await sweep.evaluate((node) => getComputedStyle(node).opacity)).toBe(
      "0",
    )

    await page.mouse.move(box.x + box.width * 0.55, box.y + box.height / 2)

    await expect
      .poll(() => sweep.evaluate((node) => getComputedStyle(node).opacity))
      .toBe("1")

    // Partway through the sweep, some keywords are dimmed and some are not.
    // Asserting both halves is what makes this a test of the sweep rather than
    // of the panel merely existing. Polled because chip opacity is transitioned
    // over 150ms, so a single read lands on interpolated values.
    await expect
      .poll(async () => {
        const opacities = await page
          .locator("[data-keyword]")
          .evaluateAll((nodes) =>
            nodes.map((node) => getComputedStyle(node).opacity),
          )
        return (
          opacities.some((value) => value === "1") &&
          opacities.some((value) => value !== "1")
        )
      })
      .toBe(true)

    // Leaving restores every keyword to full opacity.
    await movePointerAway(page)
    await expect
      .poll(() =>
        page
          .locator("[data-keyword]")
          .evaluateAll((nodes) =>
            nodes.every((node) => getComputedStyle(node).opacity === "1"),
          ),
      )
      .toBe(true)
  })

  test("issues no network request while scanning", async ({ page }) => {
    // The landing page must never drive /api/checkup: it costs two LLM passes
    // per call and is capped at 12/hour per IP.
    const requests: string[] = []
    page.on("request", (request) => requests.push(request.url()))

    const surface = page.locator("[data-scan-surface]")
    await surface.scrollIntoViewIfNeeded()
    const box = await surface.boundingBox()
    if (!box) throw new Error("scan surface has no box")

    // Confirm the sweep really runs, otherwise "made no requests" would hold
    // trivially for a pointer that never touched the panel.
    await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
    await expect
      .poll(() =>
        page
          .locator(".sr-scan-sweep")
          .evaluate((node) => getComputedStyle(node).opacity),
      )
      .toBe("1")

    for (let step = 0; step <= 10; step += 1) {
      await page.mouse.move(
        box.x + (box.width * step) / 10,
        box.y + box.height / 2,
      )
    }

    expect(requests.filter((url) => url.includes("/api/"))).toEqual([])
  })
})

test.describe("crawler assets", () => {
  test("serves robots.txt pointing at the sitemap", async ({ page, request }) => {
    await page.goto("/")
    const origin = new URL(page.url()).origin

    const response = await request.get("/robots.txt")
    expect(response.status()).toBe(200)

    const body = await response.text()
    expect(body).toContain(`Sitemap: ${origin}/sitemap.xml`)
    expect(body).toMatch(/disallow: \/dashboard/i)
    expect(body).toMatch(/disallow: \/career-watch/i)
  })

  test("serves a sitemap that includes the public pages", async ({
    page,
    request,
  }) => {
    await page.goto("/")
    const origin = new URL(page.url()).origin

    const response = await request.get("/sitemap.xml")
    expect(response.status()).toBe(200)

    const body = await response.text()
    expect(body).toContain("<urlset")
    expect(body).toContain(`<loc>${origin}/checkup</loc>`)
    expect(body).not.toContain("/dashboard")
  })

  test("serves the Open Graph image", async ({ request }) => {
    const response = await request.get("/opengraph-image.png")
    expect(response.status()).toBe(200)
    expect(response.headers()["content-type"]).toContain("image")
  })

  test("advertises an Open Graph image that actually resolves", async ({
    page,
    request,
  }) => {
    await page.goto("/")
    const origin = new URL(page.url()).origin

    const content = await page
      .locator('meta[property="og:image"]')
      .first()
      .getAttribute("content")
    expect(content).toBeTruthy()
    expect(content).toMatch(new RegExp(`^${origin}/opengraph-image`))

    const response = await request.get(new URL(content as string).pathname)
    expect(response.status()).toBe(200)
  })
})

test.describe("FAQ structured data", () => {
  test.beforeEach(async ({ page }) => {
    await page.goto("/")
  })

  test("ships every answer in the HTML rather than injecting it on open", async ({
    page,
  }) => {
    const answer = page.getByText(
      /the resume checkup runs the real analyzer with no account/i,
    )

    await expect(
      page.getByRole("heading", { level: 2, name: /questions people ask first/i }),
    ).toBeVisible()

    // The FAQ is a `<details>` accordion, so answers are collapsed at rest.
    // What matters for crawlers and answer engines is that the prose is present
    // in the served HTML rather than appearing only after a click — which is
    // why this asserts attachment, not visibility.
    await expect(answer).toBeAttached()

    // And opening the question genuinely reveals it, so the content is
    // reachable. Located by tag: Chromium does not expose `<summary>` with a
    // stable `button` role.
    await page
      .locator("summary", {
        hasText: /do i need an account to check my resume/i,
      })
      .click()
    await expect(answer).toBeVisible()
  })

  test("emits parseable FAQPage JSON-LD", async ({ page }) => {
    const scripts = await page
      .locator('script[type="application/ld+json"]')
      .allTextContents()
    expect(scripts.length).toBeGreaterThan(0)

    const faq = scripts
      .map((raw) => JSON.parse(raw) as Record<string, unknown>)
      .find((data) => data["@type"] === "FAQPage")

    expect(faq).toBeTruthy()
    const mainEntity = faq?.mainEntity as {
      "@type": string
      name: string
      acceptedAnswer: { "@type": string; text: string }
    }[]
    expect(mainEntity.length).toBeGreaterThan(0)

    for (const question of mainEntity) {
      expect(question["@type"]).toBe("Question")
      expect(question.name.trim().length).toBeGreaterThan(0)
      expect(question.acceptedAnswer["@type"]).toBe("Answer")
      expect(question.acceptedAnswer.text.trim().length).toBeGreaterThan(0)
    }
  })

  test("states the real signup credit grant in the answer", async ({ page }) => {
    // The count comes from GET /api/billing/free-tier (6 in the mock fixture),
    // so a hardcoded number in the FAQ prose would fail here. Attached rather
    // than visible: the accordion is collapsed at rest.
    await expect(page.getByText(/registering grants 6 AI credits/i)).toBeAttached()
  })
})
