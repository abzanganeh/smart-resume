import type { Page } from "@playwright/test";

/** Must match `PINNED_STICKY_TOP_PX` in `lib/marketing/scrollPin.ts`. */
const PINNED_STICKY_TOP_PX = 64;

/**
 * Scroll until the unified post-hero track reaches the given progress (0–1).
 *
 * The CTA panel is fully visible around 0.08; suggested roles around 0.35;
 * the journey handoff title around 0.7.
 */
export async function scrollPostHeroProgress(
  page: Page,
  progress: number,
): Promise<void> {
  const track = page.locator("[data-post-hero-sequence]");
  await track.scrollIntoViewIfNeeded();

  const reducedMotion = await page.evaluate(() =>
    window.matchMedia("(prefers-reduced-motion: reduce)").matches,
  );
  if (reducedMotion) {
    // Static stack: all beats are already in the document; no scroll track to drive.
    return;
  }

  await page.evaluate(
    ({ targetProgress, stickyTop }) => {
      const element = document.querySelector(
        "[data-post-hero-sequence]",
      ) as HTMLElement | null;
      if (!element) return;

      const viewportHeight = window.innerHeight;
      const travel = element.offsetHeight - viewportHeight;
      if (travel <= 0) return;

      const rect = element.getBoundingClientRect();
      const trackDocTop = rect.top + window.scrollY;
      const desiredRectTop = stickyTop - targetProgress * travel;
      window.scrollTo(0, Math.max(0, trackDocTop - desiredRectTop));
      window.dispatchEvent(new Event("scroll"));
    },
    { targetProgress: progress, stickyTop: PINNED_STICKY_TOP_PX },
  );

  await page.waitForFunction(
    (target) => {
      const element = document.querySelector("[data-post-hero-sequence]");
      const raw = element?.getAttribute("data-post-hero-progress");
      if (!raw) return false;
      return Math.abs(parseFloat(raw) - target) < 0.06;
    },
    progress,
    { timeout: 5000 },
  );
}
