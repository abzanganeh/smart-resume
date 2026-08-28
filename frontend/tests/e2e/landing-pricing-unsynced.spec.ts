import { test, expect } from "@playwright/test"

test.beforeEach(async ({ page }) => {
  await page.goto("/")
  await page.locator("#pricing").scrollIntoViewIfNeeded()
})

test("shows every paid tier without inventing a $0 price", async ({ page }) => {
  await expect(
    page.getByRole("heading", { level: 2, name: /start free, upgrade only/i }),
  ).toBeVisible()

  for (const tier of ["Weekly", "Pro", "Pro+", "Premium"]) {
    await expect(
      page.getByRole("heading", { level: 3, name: tier, exact: true }),
    ).toBeVisible()
  }

  await expect(page.getByText("$0.00")).toHaveCount(0)
  await expect(
    page.getByText(/checkout shows the live price before you pay/i).first(),
  ).toBeVisible()
})

test("still shows the free tier when paid prices are unavailable", async ({
  page,
}) => {
  await expect(
    page.getByRole("heading", { level: 3, name: "Free", exact: true }),
  ).toBeVisible()
  await expect(page.getByText("3 AI credits at signup")).toBeVisible()
})
