/** Total scroll track for the unified post-hero sequence (CTA → roles → journey handoff). */
export const POST_HERO_TRACK_VH = 320;

export interface PostHeroLayerMotion {
  /** Horizontal offset in % (positive = off-screen right). */
  x: number;
  /** Vertical offset in vh (positive = below). Used for CTA enter only. */
  y: number;
  opacity: number;
}

export interface PostHeroMotion {
  cta: PostHeroLayerMotion;
  roles: PostHeroLayerMotion;
  journeyIntro: PostHeroLayerMotion;
}

function clamp(value: number, min: number, max: number): number {
  if (!Number.isFinite(value)) return min;
  return Math.max(min, Math.min(max, value));
}

function easeOutCubic(t: number): number {
  const x = clamp(t, 0, 1);
  return 1 - Math.pow(1 - x, 3);
}

/** Progress 0→1 within [start, end] of the full track. */
function band(progress: number, start: number, end: number): number {
  if (progress <= start) return 0;
  if (progress >= end) return 1;
  return (progress - start) / (end - start);
}

/**
 * Three-beat post-hero choreography:
 * 1. CTA + career headline rise from below
 * 2. Roles card replaces from the right, exits left
 * 3. Journey title replaces from the right (hands off to JourneySection)
 */
export function postHeroMotion(progress: number): PostHeroMotion {
  const p = clamp(progress, 0, 1);

  const ctaEnter = easeOutCubic(band(p, 0, 0.13));
  const swapToRoles = easeOutCubic(band(p, 0.26, 0.4));
  const swapToJourney = easeOutCubic(band(p, 0.52, 0.66));

  const cta: PostHeroLayerMotion = { x: 0, y: 18, opacity: 0 };
  const roles: PostHeroLayerMotion = { x: 108, y: 0, opacity: 0 };
  const journeyIntro: PostHeroLayerMotion = { x: 108, y: 0, opacity: 0 };

  if (p < 0.26) {
    cta.y = 18 * (1 - ctaEnter);
    cta.opacity = ctaEnter;
  } else if (p < 0.4) {
    cta.x = -108 * swapToRoles;
    cta.y = 0;
    cta.opacity = 1 - swapToRoles;
    roles.x = 108 * (1 - swapToRoles);
    roles.opacity = swapToRoles;
  } else if (p < 0.52) {
    roles.x = 0;
    roles.opacity = 1;
  } else if (p < 0.66) {
    roles.x = -108 * swapToJourney;
    roles.opacity = 1 - swapToJourney;
    journeyIntro.x = 108 * (1 - swapToJourney);
    journeyIntro.opacity = swapToJourney;
  } else {
    journeyIntro.x = 0;
    journeyIntro.opacity = 1;
  }

  return { cta, roles, journeyIntro };
}
