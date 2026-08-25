/** Total scroll track for the unified post-hero sequence (CTA → roles). */
export const POST_HERO_TRACK_VH = 220;

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
 * Two-beat post-hero choreography:
 * 1. CTA + career headline rise from below
 * 2. Roles card replaces from the right, then releases into JourneySection
 */
export function postHeroMotion(progress: number): PostHeroMotion {
  const p = clamp(progress, 0, 1);

  const ctaEnter = easeOutCubic(band(p, 0, 0.18));
  const swapToRoles = easeOutCubic(band(p, 0.38, 0.58));

  const cta: PostHeroLayerMotion = { x: 0, y: 18, opacity: 0 };
  const roles: PostHeroLayerMotion = { x: 108, y: 0, opacity: 0 };

  if (p < 0.38) {
    cta.y = 18 * (1 - ctaEnter);
    cta.opacity = ctaEnter;
  } else if (p < 0.58) {
    cta.x = -108 * swapToRoles;
    cta.y = 0;
    cta.opacity = 1 - swapToRoles;
    roles.x = 108 * (1 - swapToRoles);
    roles.opacity = swapToRoles;
  } else {
    roles.x = 0;
    roles.opacity = 1;
  }

  return { cta, roles };
}
