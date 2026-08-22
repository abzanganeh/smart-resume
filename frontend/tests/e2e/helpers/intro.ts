import type { Page } from "@playwright/test"

/** Must match `INTRO_SEEN_KEY` in `lib/brand.ts`. */
const INTRO_SEEN_KEY = "flintapply:intro-seen"

/**
 * Mark the landing intro as already played, before any page script runs.
 *
 * The intro is a full-viewport `position: fixed` overlay at z-index 100 that
 * swallows pointer events for its whole duration. Specs that drive the page
 * with `page.mouse.move` — which performs no actionability check, unlike
 * `locator.hover()` — otherwise land the cursor on the overlay instead of the
 * element under test, and the interaction silently never registers.
 *
 * Scrolling also dismisses the intro, so scroll-driven specs tend to pass by
 * accident. Suppressing it up front makes that deterministic too.
 *
 * Call before `page.goto`.
 */
export async function suppressIntro(page: Page): Promise<void> {
  await page.addInitScript((key) => {
    try {
      sessionStorage.setItem(key, "1")
    } catch {
      // Storage can be unavailable; the intro stays dismissable by other means.
    }
  }, INTRO_SEEN_KEY)
}
