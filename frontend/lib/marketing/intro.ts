/**
 * Timing and copy for the landing intro.
 *
 * A full-viewport intro is a cost as well as a flourish: it delays the first
 * thing a visitor came for. Three rules keep it from becoming a barrier.
 *
 *   - It plays once per session, never on every navigation.
 *   - It never plays under `prefers-reduced-motion: reduce`.
 *   - It is short, skippable, and the landing content is fully rendered
 *     underneath it the whole time — so a crawler, a screen reader, and a
 *     visitor who dismisses it immediately all see the same page.
 */

export const INTRO_LOGO_MS = 900;
export const INTRO_TOTAL_MS = 2_400;

/** Session key, so a second page view in the same tab goes straight to content. */
export const INTRO_SEEN_KEY = "taliocv:intro-seen";

/**
 * Greeting copy. States what the product does, not just what it is called, and
 * claims no outcome — "finds the roles you fit" is a description of a feature,
 * whereas a hit rate or a guarantee would be a number we cannot stand behind.
 */
export const INTRO_GREETING = {
  line: "Hi, I'm TalioCV.",
  sub: "Your AI assistant for finding the jobs you actually fit and building the resume that gets you there.",
} as const;

export type IntroPhase = "logo" | "greeting" | "done";

export interface IntroConditions {
  prefersReducedMotion: boolean;
  alreadyPlayed: boolean;
}

export function shouldPlayIntro({
  prefersReducedMotion,
  alreadyPlayed,
}: IntroConditions): boolean {
  return !prefersReducedMotion && !alreadyPlayed;
}

/** Phase for a given elapsed time. Total, so a stalled frame cannot wedge it. */
export function introPhaseAt(elapsedMs: number): IntroPhase {
  if (!Number.isFinite(elapsedMs) || elapsedMs < INTRO_LOGO_MS) return "logo";
  if (elapsedMs < INTRO_TOTAL_MS) return "greeting";
  return "done";
}
