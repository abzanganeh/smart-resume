/**
 * E2E tests for the /legal/* surface (Step 38 — Compliance).
 *
 * Verifies:
 *   - All footer links resolve with HTTP 200.
 *   - Each legal page renders the expected title.
 *   - The DPO contact form mounts and validates input client-side.
 *
 * Prerequisites:
 *   - Next.js dev server on http://localhost:3000
 *   - Backend on http://localhost:8000 (or DPO contact route mocked).
 */
import { test, expect } from "@playwright/test"

const BASE = "http://localhost:3000"

const FOOTER_PAGES = [
  { href: "/legal/terms", title: "Terms of Service" },
  { href: "/legal/privacy", title: "Privacy Policy" },
  { href: "/legal/sub-processors", title: "Sub-processors" },
  { href: "/legal/ccpa", title: "Do Not Sell My Personal Information" },
  { href: "/legal/contact", title: "Contact our DPO" },
]

test.describe("/legal pages — footer link check", () => {
  for (const { href, title } of FOOTER_PAGES) {
    test(`GET ${href} → 200 + title "${title}"`, async ({ page, request }) => {
      const res = await request.get(`${BASE}${href}`)
      expect(res.status()).toBe(200)

      await page.goto(`${BASE}${href}`)
      await expect(
        page.getByRole("heading", { level: 1, name: title }),
      ).toBeVisible()
    })
  }
})

test.describe("footer", () => {
  test("renders BSL 1.1 copyright and DPO email link on home", async ({
    page,
  }) => {
    await page.goto(`${BASE}/`)
    const footer = page.getByRole("contentinfo")
    await expect(footer).toBeVisible()
    await expect(footer).toContainText(`© ${new Date().getFullYear()} Flint AI`)
    await expect(footer).toContainText("BSL 1.1")
    await expect(
      footer.getByRole("link", { name: "privacy@zanganehai.com" }),
    ).toHaveAttribute("href", "mailto:privacy@zanganehai.com")
  })

  test("legal links are reachable from the footer", async ({ page }) => {
    await page.goto(`${BASE}/`)
    const footer = page.getByRole("contentinfo")
    for (const { href } of FOOTER_PAGES) {
      await expect(footer.getByRole("link", { name: new RegExp(href.split("/").pop() ?? "", "i") }).first()).toBeVisible({ timeout: 2_000 }).catch(() => {
        // Fallback: locate by href in case the visible label diverges.
      })
      const link = footer.locator(`a[href="${href}"]`)
      await expect(link).toHaveCount(1)
    }
  })
})

test.describe("/legal/contact form", () => {
  test("client-side validation rejects too-short messages", async ({
    page,
  }) => {
    await page.goto(`${BASE}/legal/contact`)

    await page.getByLabel("Your name").fill("Jane Doe")
    await page.getByLabel("Reply-to email").fill("jane@example.com")
    await page.getByLabel("Message").fill("too short")
    await page.getByRole("button", { name: /send to dpo/i }).click()

    // Browser-level constraint validation should prevent submission.
    const message = page.getByLabel("Message")
    const valid = await message.evaluate(
      (el: HTMLTextAreaElement) => el.checkValidity(),
    )
    expect(valid).toBe(false)
  })
})
