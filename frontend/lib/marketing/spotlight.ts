/**
 * Pointer geometry for the capability spotlight.
 *
 * Pure and DOM-free on purpose: this repo has no jsdom, so the only way to get
 * real coverage on the interaction is to keep the maths out of the component.
 * The component measures rects and feeds them in.
 *
 * Every function is total — a pointer can leave the panel between a
 * `pointermove` and the next animation frame, and a rect can be measured as
 * zero-sized during layout, so out-of-range input must produce a sane value
 * rather than `NaN` or an off-element gradient.
 */

export interface SpotlightPoint {
  x: number;
  y: number;
}

export interface SpotlightRect {
  left: number;
  top: number;
  width: number;
  height: number;
}

export interface SpotlightTilt {
  rotateX: number;
  rotateY: number;
}

export interface MotionCapability {
  prefersReducedMotion: boolean;
  hasFinePointer: boolean;
}

const clamp01 = (value: number): number => {
  if (!Number.isFinite(value)) return 0.5;
  if (value < 0) return 0;
  if (value > 1) return 1;
  return value;
};

/** `-0` and `0` are different values to `assert.deepStrictEqual` and to CSS. */
const withoutNegativeZero = (value: number): number => (value === 0 ? 0 : value);

const hasArea = (rect: SpotlightRect): boolean =>
  Number.isFinite(rect.width) &&
  Number.isFinite(rect.height) &&
  rect.width > 0 &&
  rect.height > 0;

/**
 * Pointer position as a fraction of the rect, clamped to the unit square.
 * A degenerate rect resolves to the centre so the spotlight sits still rather
 * than jumping to a corner while layout settles.
 */
export function normalizedPosition(
  point: SpotlightPoint,
  rect: SpotlightRect,
): SpotlightPoint {
  if (!hasArea(rect)) return { x: 0.5, y: 0.5 };
  return {
    x: clamp01((point.x - rect.left) / rect.width),
    y: clamp01((point.y - rect.top) / rect.height),
  };
}

/**
 * Index of the card whose centre is nearest the pointer, or `null` when there
 * are no cards. Ties resolve to the earlier card so selection never flickers
 * between two equidistant neighbours.
 */
export function nearestIndex(
  point: SpotlightPoint,
  rects: readonly SpotlightRect[],
): number | null {
  let best: number | null = null;
  let bestDistance = Number.POSITIVE_INFINITY;

  rects.forEach((rect, index) => {
    const centreX = rect.left + rect.width / 2;
    const centreY = rect.top + rect.height / 2;
    const dx = point.x - centreX;
    const dy = point.y - centreY;
    const distance = dx * dx + dy * dy;
    if (distance < bestDistance) {
      bestDistance = distance;
      best = index;
    }
  });

  return best;
}

/**
 * Tilt for a card, from where the pointer sits inside it. Bounded by `maxDeg`
 * in both axes because `normalizedPosition` clamps first.
 */
export function tiltFor(
  point: SpotlightPoint,
  rect: SpotlightRect,
  maxDeg: number,
): SpotlightTilt {
  const { x, y } = normalizedPosition(point, rect);
  return {
    rotateX: withoutNegativeZero((0.5 - y) * 2 * maxDeg),
    rotateY: withoutNegativeZero((x - 0.5) * 2 * maxDeg),
  };
}

/**
 * Whether to run pointer-driven motion at all. Touch devices have no hover to
 * follow, and a reduced-motion request is honoured without disabling selection.
 */
export function shouldAnimate({
  prefersReducedMotion,
  hasFinePointer,
}: MotionCapability): boolean {
  return !prefersReducedMotion && hasFinePointer;
}
