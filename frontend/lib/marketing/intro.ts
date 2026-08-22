/**
 * Timing and motion for the landing intro.
 *
 * Cumulative reveal: each layer zooms/fades in over its own window and stays
 * visible. A final hold keeps all three on screen before the overlay dismisses.
 *
 * Adjust `INTRO_TIMING` when tuning — the overlay reads these values directly.
 */

export { INTRO_GREETING, INTRO_SEEN_KEY } from "@/lib/brand";

/** All phase durations in milliseconds. Sum equals `INTRO_TOTAL_MS`. */
export const INTRO_TIMING = {
  /** Icon mark emerges. */
  logoInMs: 3_000,
  /** FlintApply wordmark emerges beneath the icon. */
  wordmarkInMs: 3_000,
  /** Greeting copy emerges beneath the lockup. */
  greetingInMs: 3_000,
  /** All three visible, no further motion, before dismiss. */
  holdMs: 3_000,
} as const;

export const INTRO_EMERGE_MS =
  INTRO_TIMING.logoInMs +
  INTRO_TIMING.wordmarkInMs +
  INTRO_TIMING.greetingInMs;

export const INTRO_TOTAL_MS = INTRO_EMERGE_MS + INTRO_TIMING.holdMs;

/** @deprecated Prefer `INTRO_TIMING.logoInMs`. */
export const INTRO_LOGO_MS = INTRO_TIMING.logoInMs;

/** @deprecated Prefer `INTRO_TIMING.greetingInMs + INTRO_TIMING.holdMs`. */
export const INTRO_GREETING_MS =
  INTRO_TIMING.greetingInMs + INTRO_TIMING.holdMs;

export type IntroPhase =
  | "logo-in"
  | "wordmark-in"
  | "greeting-in"
  | "hold"
  | "done";

export interface IntroConditions {
  prefersReducedMotion: boolean;
  alreadyPlayed: boolean;
}

/** Visual size multiplier for intro layout classes (1 = design default). */
export const INTRO_SIZE_SCALE = 2;

/** Motion targets — entrance animates from `*StartScale` to `*EndScale` (always 1). */
export const INTRO_MOTION = {
  logoMarkStartScale: 0.45,
  logoMarkEndScale: 1,
  wordmarkStartScale: 0.85,
  wordmarkEndScale: 1,
  greetingStartScale: 0.85,
  greetingEndScale: 1,
} as const;

export interface LayerMotion {
  scale: number;
  opacity: number;
}

export interface IntroMotionFrame {
  phase: IntroPhase;
  logoMark: LayerMotion;
  wordmark: LayerMotion;
  greeting: LayerMotion;
}

export function shouldPlayIntro({
  prefersReducedMotion,
  alreadyPlayed,
}: IntroConditions): boolean {
  return !prefersReducedMotion && !alreadyPlayed;
}

function clamp01(value: number): number {
  if (!Number.isFinite(value)) return 0;
  if (value <= 0) return 0;
  if (value >= 1) return 1;
  return value;
}

function lerp(from: number, to: number, t: number): number {
  return from + (to - from) * clamp01(t);
}

function easeOutCubic(t: number): number {
  const x = clamp01(t);
  return 1 - (1 - x) ** 3;
}

const HIDDEN: LayerMotion = { scale: INTRO_MOTION.wordmarkStartScale, opacity: 0 };

const FULL_LOGO: LayerMotion = {
  scale: INTRO_MOTION.logoMarkEndScale,
  opacity: 1,
};

const FULL_WORDMARK: LayerMotion = {
  scale: INTRO_MOTION.wordmarkEndScale,
  opacity: 1,
};

const FULL_GREETING: LayerMotion = {
  scale: INTRO_MOTION.greetingEndScale,
  opacity: 1,
};

function entranceMotion(
  elapsedInPhase: number,
  phaseDurationMs: number,
  startScale: number,
  endScale: number,
): LayerMotion {
  const progress = clamp01(elapsedInPhase / phaseDurationMs);
  const eased = easeOutCubic(progress);
  return {
    scale: lerp(startScale, endScale, eased),
    opacity: eased,
  };
}

const GREETING_START_MS =
  INTRO_TIMING.logoInMs + INTRO_TIMING.wordmarkInMs;
const HOLD_START_MS = GREETING_START_MS + INTRO_TIMING.greetingInMs;

/** Phase for a given elapsed time. Total, so a stalled frame cannot wedge it. */
export function introPhaseAt(elapsedMs: number): IntroPhase {
  if (!Number.isFinite(elapsedMs) || elapsedMs < 0) return "logo-in";
  if (elapsedMs < INTRO_TIMING.logoInMs) return "logo-in";
  if (elapsedMs < GREETING_START_MS) return "wordmark-in";
  if (elapsedMs < HOLD_START_MS) return "greeting-in";
  if (elapsedMs < INTRO_TOTAL_MS) return "hold";
  return "done";
}

/** Normalized progress within the current phase, 0–1. */
export function introPhaseProgress(elapsedMs: number): number {
  const phase = introPhaseAt(elapsedMs);
  if (phase === "done") return 1;

  const { logoInMs, wordmarkInMs, greetingInMs, holdMs } = INTRO_TIMING;

  if (phase === "logo-in") {
    return clamp01(elapsedMs / logoInMs);
  }
  if (phase === "wordmark-in") {
    return clamp01((elapsedMs - logoInMs) / wordmarkInMs);
  }
  if (phase === "greeting-in") {
    return clamp01((elapsedMs - GREETING_START_MS) / greetingInMs);
  }
  return clamp01((elapsedMs - HOLD_START_MS) / holdMs);
}

/** Scale/opacity for each layer at a given elapsed time. */
export function introMotionAt(elapsedMs: number): IntroMotionFrame {
  const phase = introPhaseAt(elapsedMs);
  const { logoInMs, wordmarkInMs, greetingInMs } = INTRO_TIMING;
  const wordmarkStartMs = logoInMs;

  if (phase === "done" || phase === "hold") {
    return {
      phase,
      logoMark: FULL_LOGO,
      wordmark: FULL_WORDMARK,
      greeting: FULL_GREETING,
    };
  }

  const logoMark =
    elapsedMs >= logoInMs
      ? FULL_LOGO
      : entranceMotion(
          elapsedMs,
          logoInMs,
          INTRO_MOTION.logoMarkStartScale,
          INTRO_MOTION.logoMarkEndScale,
        );

  let wordmark: LayerMotion = HIDDEN;
  if (elapsedMs >= GREETING_START_MS) {
    wordmark = FULL_WORDMARK;
  } else if (elapsedMs >= wordmarkStartMs) {
    wordmark = entranceMotion(
      elapsedMs - wordmarkStartMs,
      wordmarkInMs,
      INTRO_MOTION.wordmarkStartScale,
      INTRO_MOTION.wordmarkEndScale,
    );
  }

  let greeting: LayerMotion = HIDDEN;
  if (elapsedMs >= HOLD_START_MS) {
    greeting = FULL_GREETING;
  } else if (elapsedMs >= GREETING_START_MS) {
    greeting = entranceMotion(
      elapsedMs - GREETING_START_MS,
      greetingInMs,
      INTRO_MOTION.greetingStartScale,
      INTRO_MOTION.greetingEndScale,
    );
  }

  return { phase, logoMark, wordmark, greeting };
}
