/**
 * Canonical FlintApply branding — single source for user-facing product name.
 *
 * Legal pages and the Flint desktop import flow may still say TalioCV until
 * those are explicitly updated. Everything else should import from here.
 */

export const PRODUCT_NAME = "FlintApply" as const;

export const COMPANY_LINE = "by The Flint AI" as const;

export const COMPANY_NAME = "Flint AI" as const;

export const COMPANY_URL = "https://theflintai.com" as const;

export const PRIVACY_EMAIL = "privacy@zanganehai.com" as const;

/** Text wordmark PNGs — replace in place when art updates. */
export const WORDMARK_LIGHT_SRC = "/brand/flintapply-wordmark-light.png" as const;
export const WORDMARK_DARK_SRC = "/brand/flintapply-wordmark-dark.png" as const;

/**
 * Framed product marketing shot — used by `ProductScreenshot` in inline
 * capability strips. Kept on the JPG because that shot is a crawler-friendly
 * flat render, not the atmospheric hero art.
 */
export const HERO_PRODUCT_SHOT_SRC = "/marketing/flintapply-hero.jpg" as const;

/**
 * Full-bleed pinned hero art. Dark 3D render of a document radiating into
 * hex nodes; transparent PNG so the wash underneath shines through the edges.
 * Kept separate from `HERO_PRODUCT_SHOT_SRC` because that constant is still
 * used by the plain framed screenshot and swapping it there would replace a
 * literal product screenshot with a stylised render.
 */
export const HERO_PRODUCT_SRC = "/marketing/hero-image.png" as const;

/** Session key — intro plays once per tab session. */
export const INTRO_SEEN_KEY = "flintapply:intro-seen";

export const INTRO_GREETING = {
  line: `Hi, I'm ${PRODUCT_NAME}.`,
  sub: "Your AI assistant for finding the jobs you actually fit and building the resume that gets you there.",
} as const;

export const METADATA_TITLE =
  `${PRODUCT_NAME} — AI resume tailoring, ATS optimization & job search` as const;

export const METADATA_DESCRIPTION =
  "Discover the job titles you actually fit, then tailor an ATS-optimized resume to every job description. Master resume, cover letters, job search, and application tracking in one place." as const;

export const METADATA_OG_TITLE = PRODUCT_NAME;

export const METADATA_OG_DESCRIPTION =
  "Find the roles you fit, then tailor an ATS-optimized resume for each one." as const;

export function productScreenshotAlt(): string {
  return `${PRODUCT_NAME} — AI resume tailoring and ATS optimization, framed brand mockup`;
}

/**
 * Legacy TalioCV filenames still served until FlintApply art ships.
 * Replace each path and remove the row when the new asset lands.
 */
export const LEGACY_ASSET_REPLACEMENTS = [
  { path: "/brand/taliocv-2-lockup.png", replaceWith: "Retired — use flintapply-wordmark-*.png" },
  { path: "/brand/taliocv-2.svg", replaceWith: "FlintApply vector lockup" },
  { path: "/brand/mark.png", replaceWith: "FlintApply app icon" },
  { path: "/brand/mark.svg", replaceWith: "FlintApply icon SVG" },
  { path: "/marketing/taliocv-hero.jpg", replaceWith: "Retired — use flintapply-hero.jpg" },
  { path: "/brand/taliocv-mini.svg", replaceWith: "FlintApply compact mark" },
  { path: "/brand/taliocv-1.svg", replaceWith: "Retire or replace with FlintApply mark set" },
  { path: "/brand/taliocv-2-mini.svg", replaceWith: "FlintApply mini lockup" },
] as const;
