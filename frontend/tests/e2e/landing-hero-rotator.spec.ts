/**
 * E2E for M22: intro backstop + hero strength rotator (Section 11l).
 *
 *   E2E_MOCK_API=1 PLAYWRIGHT_PORT=3100 pnpm exec playwright test tests/e2e/landing-hero-rotator.spec.ts
 */
import { test, expect } from "@playwright/test";
import {
  INTRO_DISMISS_SLACK_MS,
  INTRO_FADE_MS,
  INTRO_TOTAL_MS,
} from "@/lib/marketing/intro";

const INTRO_DISMISS_DEADLINE_MS =
  INTRO_TOTAL_MS + INTRO_DISMISS_SLACK_MS + INTRO_FADE_MS + 500;

test.describe("landing intro backstop", () => {
  test("dismisses without user input when animation frames never fire", async ({
    page,
  }) => {
    await page.addInitScript(() => {
      sessionStorage.removeItem("flintapply:intro-seen");
      window.requestAnimationFrame = () => 0;
    });

    await page.goto("/?intro=1");

    const overlay = page.locator("[data-intro-phase]");
    await expect(overlay).toBeVisible();
    await expect(overlay).toHaveCount(0, { timeout: INTRO_DISMISS_DEADLINE_MS });
  });
});

test.describe("hero strength rotator", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem("flintapply:intro-seen", "1");
    });
    await page.goto("/");
  });

  test("ships every strength line in the HTML source", async ({ page }) => {
    for (const line of [
      /speak your career out loud/i,
      /ten realistic job titles/i,
      /must-have keyword/i,
      /before-and-after ATS score/i,
      /cover letters drawn from the same evidence/i,
      /every application on one board/i,
    ]) {
      await expect(page.getByText(line).first()).toBeAttached();
    }
  });

  test("keeps the company-watch headline fixed", async ({ page }) => {
    await expect(
      page.getByRole("heading", { level: 1, name: /name the companies/i }),
    ).toBeVisible();
  });

  test("advances the active strength line over time", async ({ page }) => {
    const stage = page.locator(".hero-strength-rotator__stage");
    await expect(stage).toHaveAttribute("data-active-index", "0");

    await expect
      .poll(async () => stage.getAttribute("data-active-index"), {
        timeout: 12_000,
      })
      .not.toBe("0");
  });

  test("pauses rotation from the control", async ({ page }) => {
    const stage = page.locator(".hero-strength-rotator__stage");
    const pause = page.getByRole("button", { name: /pause strength rotation/i });

    await pause.click();
    await expect(pause).toHaveAttribute("aria-pressed", "true");

    const indexBefore = await stage.getAttribute("data-active-index");
    await page.waitForTimeout(2_500);
    await expect(stage).toHaveAttribute("data-active-index", indexBefore ?? "0");
  });
});
