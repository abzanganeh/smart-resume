/** Total scroll track for the unified post-hero sequence (CTA → roles → proof). */
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
  proof: PostHeroLayerMotion;
}

/** Scroll bands where one beat's card swaps for the next. */
const SWAP_TO_ROLES: readonly [number, number] = [0.26, 0.4];
const SWAP_TO_PROOF: readonly [number, number] = [0.52, 0.66];

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
 * 3. Proof card (deterministic scoring) replaces from the right
 */
export function postHeroMotion(progress: number): PostHeroMotion {
  const p = clamp(progress, 0, 1);

  const ctaEnter = easeOutCubic(band(p, 0, 0.13));
  const swapToRoles = easeOutCubic(band(p, ...SWAP_TO_ROLES));
  const swapToProof = easeOutCubic(band(p, ...SWAP_TO_PROOF));

  const cta: PostHeroLayerMotion = { x: 0, y: 18, opacity: 0 };
  const roles: PostHeroLayerMotion = { x: 108, y: 0, opacity: 0 };
  const proof: PostHeroLayerMotion = { x: 108, y: 0, opacity: 0 };

  if (p < SWAP_TO_ROLES[0]) {
    cta.y = 18 * (1 - ctaEnter);
    cta.opacity = ctaEnter;
  } else if (p < SWAP_TO_ROLES[1]) {
    cta.x = -108 * swapToRoles;
    cta.y = 0;
    cta.opacity = 1 - swapToRoles;
    roles.x = 108 * (1 - swapToRoles);
    roles.opacity = swapToRoles;
  } else if (p < SWAP_TO_PROOF[0]) {
    roles.x = 0;
    roles.opacity = 1;
  } else if (p < SWAP_TO_PROOF[1]) {
    roles.x = -108 * swapToProof;
    roles.opacity = 1 - swapToProof;
    proof.x = 108 * (1 - swapToProof);
    proof.opacity = swapToProof;
  } else {
    proof.x = 0;
    proof.opacity = 1;
  }

  return { cta, roles, proof };
}
