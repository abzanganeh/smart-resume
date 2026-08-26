/**
 * E2E for M22: intro backstop + scroll-linked hero messages (Section 11l).
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

test.describe("hero scroll messages", () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      sessionStorage.setItem("flintapply:intro-seen", "1");
    });
    await page.goto("/");
  });

  test("ships every hero message in the HTML source", async ({ page }) => {
    for (const line of [
      /name the companies/i,
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

  test("starts on the company-watch message", async ({ page }) => {
    const stage = page.locator(".hero-message-rotator__stage");
    await expect(stage).toHaveAttribute("data-active-index", "0");
    await expect(
      page.getByRole("heading", { level: 1, name: /name the companies/i }),
    ).toBeVisible();
  });

  test("advances the active message while scrolling the hero track", async ({
    page,
  }) => {
    const track = page.locator("[data-hero-scroll-track]");
    await expect(track).toBeVisible();

    const stage = page.locator(".hero-message-rotator__stage");
    await expect(stage).toHaveAttribute("data-active-index", "0");

    await page.evaluate(() => {
      const el = document.querySelector("[data-hero-scroll-track]");
      if (!el) return;
      const top =
        el.getBoundingClientRect().top + window.scrollY - 64 + el.clientHeight * 0.35;
      window.scrollTo({ top, behavior: "instant" });
    });

    await expect
      .poll(async () => stage.getAttribute("data-active-index"), {
        timeout: 5_000,
      })
      .not.toBe("0");
  });

  test("renders exactly one visible h1 for the active message", async ({
    page,
  }) => {
    await expect(page.getByRole("heading", { level: 1 })).toHaveCount(1);
  });

  test("attaches all seven message sets to the DOM", async ({ page }) => {
    await expect(page.locator("[data-message-id]")).toHaveCount(7);
    await expect(page.locator(".hero-message-rotator .sr-only li")).toHaveCount(7);
  });

  test("uses a static hero panel without a scroll track under reduced motion", async ({
    page,
  }) => {
    await page.emulateMedia({ reducedMotion: "reduce" });
    await page.reload();

    await expect(page.locator("[data-hero-scroll-track]")).toHaveCount(0);
    await expect(page.locator(".hero-message-rotator__stage")).toBeVisible();
    await expect(
      page.getByRole("heading", { level: 1, name: /name the companies/i }),
    ).toBeVisible();
  });
});

test.describe("landing security headers", () => {
  test("emits OWASP A02 headers on the public landing route", async ({ page }) => {
    const response = await page.goto("/");
    expect(response).not.toBeNull();
    const headers = response!.headers();
    expect(headers["content-security-policy"]).toContain("frame-ancestors 'none'");
    expect(headers["content-security-policy"]).toMatch(/'nonce-[-A-Za-z0-9+/=]+'/);
    expect(headers["content-security-policy"]).toContain("'strict-dynamic'");
    expect(headers["content-security-policy-report-only"]).toBeUndefined();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["referrer-policy"]).toBe("strict-origin-when-cross-origin");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["permissions-policy"]).toContain("camera=()");
  });
});
