/**
 * The unsynced-price fallback on the landing page.
 *
 * This is the state of any environment where PlanConfig rows exist but the
 * Stripe price sync has not run yet — `bootstrap.py` seeds `amount_cents` to 0.
 * Rendering that as "$0.00" would advertise a paid tier as free, so the section
 * must defer to a "see plans" card instead.
 *
 * Run separately from the main smoke suite, because Next caches the price
 * response per URL (`revalidate: 60`) and would otherwise serve the synced
 * fixture that `landing.spec.ts` already primed:
 *
 *   pnpm run test:e2e:pricing-unsynced
 *
 * The npm script clears both cache locations. CI runs `next start`, which caches
 * under `.next/cache`, while a local run uses `next dev`, which caches under
 * `.next/dev/cache` — clearing only the first makes this spec pass in CI and
 * fail locally with a stale synced fixture.
 */
import { test, expect } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/")
})

test("defers pricing instead of rendering an unsynced plan as free", async ({
  page,
}) => {
  // Anchor on the section actually being present, so the absence assertions
  // below cannot pass just because the page failed to render.
  await expect(
    page.getByRole("heading", { level: 2, name: /start free, upgrade only/i }),
  ).toBeVisible()

  await expect(
    page.getByRole("heading", { level: 3, name: "Paid plans", exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole("link", { name: /see plans and pricing/i }),
  ).toBeVisible()

  await expect(page.getByText("$0.00")).toHaveCount(0)
  await expect(
    page.getByRole("heading", { level: 3, name: "Pro", exact: true }),
  ).toHaveCount(0)
})

test("still shows the free tier when paid prices are unavailable", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { level: 3, name: "Free", exact: true }),
  ).toBeVisible()
  await expect(page.getByText("6 AI credits at signup")).toBeVisible()
})
