/** Cross-fade interval for the hero strength rotator (~10 seconds). */
export const HERO_STRENGTH_ROTATION_MS = 10_000;

export function nextStrengthIndex(currentIndex: number, count: number): number {
  if (count <= 0) return 0;
  if (currentIndex < 0 || currentIndex >= count) return 0;
  return (currentIndex + 1) % count;
}

export interface RotationAdvanceInput {
  now: number;
  lastAdvanceAt: number;
  intervalMs: number;
  paused: boolean;
  documentHidden: boolean;
  count: number;
}

/** Whether the rotator should advance to the next line on this tick. */
export function shouldAdvanceStrengthRotation(input: RotationAdvanceInput): boolean {
  const { now, lastAdvanceAt, intervalMs, paused, documentHidden, count } = input;
  if (count <= 1) return false;
  if (paused || documentHidden) return false;
  if (!Number.isFinite(now) || !Number.isFinite(lastAdvanceAt)) return false;
  return now - lastAdvanceAt >= intervalMs;
}

/**
 * After a tab becomes visible again, resume from the current index without
 * bursting through every interval that elapsed while hidden.
 */
export function resyncRotationClock(now: number): number {
  return Number.isFinite(now) ? now : 0;
}
