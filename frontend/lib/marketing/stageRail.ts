/**
 * Colour identity and scroll geometry for the journey rail.
 *
 * Pure and DOM-free for the same reason as `spotlight.ts`: there is no jsdom in
 * this repo, so the maths has to live outside the component to be testable. The
 * component measures rects and feeds them in.
 *
 * Every function is total. A rect can be measured as zero-height while layout
 * settles, and a scroll handler can fire before the section has any size, so
 * out-of-range input must produce a usable number rather than `NaN`.
 */

export const STAGE_LETTERS = ["A", "B", "C", "D", "E", "F"] as const;

export interface StageTheme {
  /** Stable identifier for the hue, used to assert one colour per stage. */
  accent: string;
  /** Paired light/dark text classes — both tiers clear AA on our surfaces. */
  text: string;
  /** Solid fill for the rail node. */
  dot: string;
  /** Letter badge background. */
  badge: string;
  /** Border applied while the stage is emphasised. */
  border: string;
  /** `rgb()` channels for the rail gradient, written into a CSS variable. */
  glow: string;
}

const FALLBACK_THEME: StageTheme = {
  accent: "slate",
  text: "text-slate-700 dark:text-slate-300",
  dot: "bg-slate-400",
  badge: "bg-slate-100 dark:bg-slate-800",
  border: "border-slate-400/70",
  glow: "148 163 184",
};

/**
 * One hue per stage, ordered as the arc from telling your story to an offer.
 * Colour carries no meaning on its own — every stage still states its access
 * level in words — so this is decoration, not information.
 */
const THEMES: Record<string, StageTheme> = {
  story: {
    accent: "indigo",
    text: "text-indigo-700 dark:text-indigo-400",
    dot: "bg-indigo-500",
    badge: "bg-indigo-50 dark:bg-indigo-950/60",
    border: "border-indigo-400/70",
    glow: "99 102 241",
  },
  discover: {
    accent: "violet",
    text: "text-violet-700 dark:text-violet-400",
    dot: "bg-violet-500",
    badge: "bg-violet-50 dark:bg-violet-950/60",
    border: "border-violet-400/70",
    glow: "139 92 246",
  },
  jobs: {
    accent: "sky",
    text: "text-sky-700 dark:text-sky-400",
    dot: "bg-sky-500",
    badge: "bg-sky-50 dark:bg-sky-950/60",
    border: "border-sky-400/70",
    glow: "14 165 233",
  },
  tailor: {
    accent: "amber",
    text: "text-amber-700 dark:text-amber-400",
    dot: "bg-amber-500",
    badge: "bg-amber-50 dark:bg-amber-950/60",
    border: "border-amber-400/70",
    glow: "245 158 11",
  },
  apply: {
    accent: "emerald",
    text: "text-emerald-700 dark:text-emerald-400",
    dot: "bg-emerald-500",
    badge: "bg-emerald-50 dark:bg-emerald-950/60",
    border: "border-emerald-400/70",
    glow: "16 185 129",
  },
  track: {
    accent: "rose",
    text: "text-rose-700 dark:text-rose-400",
    dot: "bg-rose-500",
    badge: "bg-rose-50 dark:bg-rose-950/60",
    border: "border-rose-400/70",
    glow: "244 63 94",
  },
};

export function stageTheme(id: string): StageTheme {
  return THEMES[id] ?? FALLBACK_THEME;
}

/**
 * Visual index for a stage. Letters mirror the lettered service grids this
 * pattern comes from; past the alphabet slice it degrades to a number so adding
 * a seventh stage cannot blank the badge.
 */
export function stageLetter(index: number): string {
  if (!Number.isInteger(index) || index < 0) return "1";
  return STAGE_LETTERS[index] ?? String(index + 1);
}

export interface RailRect {
  /** Section top, relative to the viewport (i.e. `getBoundingClientRect`). */
  top: number;
  height: number;
}

/**
 * How far the reader has moved through the section, from 0 to 1.
 *
 * The read line is the viewport midpoint rather than its top edge, so the rail
 * fills in step with whatever the reader is actually looking at instead of
 * completing while the last stage is still below the fold.
 */
export function railProgress(rect: RailRect, viewportHeight: number): number {
  if (!Number.isFinite(rect.top) || !Number.isFinite(rect.height)) return 0;
  if (!Number.isFinite(viewportHeight) || rect.height <= 0) return 0;

  const readLine = viewportHeight / 2;
  const travelled = (readLine - rect.top) / rect.height;

  if (travelled < 0) return 0;
  if (travelled > 1) return 1;
  return travelled;
}

/**
 * Progress through a pinned scrollytelling track, from 0 to 1.
 *
 * `railProgress` measures a normal-flow section against the viewport midpoint,
 * which is wrong for a track holding a sticky child: by the time the child
 * pins, the midpoint has already travelled half a viewport into the track, so
 * the first stage is partly consumed before the visitor has scrolled at all.
 *
 * This maps the exact window during which the child stays pinned — 0 when the
 * track top reaches the viewport top, 1 when its bottom reaches the viewport
 * bottom — so the first and last stages both get their full share.
 *
 * Total, like every function here: a track shorter than the viewport has no
 * travel to divide by, and resolves by which side of the fold it sits on.
 */
export function pinnedProgress(rect: RailRect, viewportHeight: number): number {
  if (!Number.isFinite(rect.top) || !Number.isFinite(rect.height)) return 0;
  if (!Number.isFinite(viewportHeight)) return 0;

  const travel = rect.height - viewportHeight;
  if (travel <= 0) return rect.top <= 0 ? 1 : 0;

  const moved = -rect.top / travel;
  // `<= 0` rather than `< 0` so a track flush with the viewport top returns a
  // normalized 0 instead of the -0 that negating a zero `top` produces.
  if (moved <= 0) return 0;
  if (moved > 1) return 1;
  return moved;
}

/**
 * Like `pinnedProgress`, but accounts for a sticky panel offset below the nav
 * (e.g. `top-16`). Progress is 0 when the track top reaches the sticky line
 * and 1 when the track bottom reaches the viewport bottom.
 */
export function pinnedProgressForSticky(
  rect: RailRect,
  viewportHeight: number,
  stickyTop: number,
): number {
  if (!Number.isFinite(rect.top) || !Number.isFinite(rect.height)) return 0;
  if (!Number.isFinite(viewportHeight) || !Number.isFinite(stickyTop)) return 0;

  const travel = rect.height - viewportHeight;
  if (travel <= 0) return rect.top <= stickyTop ? 1 : 0;

  const moved = (stickyTop - rect.top) / travel;
  if (moved <= 0) return 0;
  if (moved > 1) return 1;
  return moved;
}

/** Stage the read line currently sits on, or `null` when there are none. */
export function activeStageFromProgress(
  progress: number,
  count: number,
): number | null {
  if (!Number.isInteger(count) || count <= 0) return null;
  if (!Number.isFinite(progress) || progress <= 0) return 0;
  if (progress >= 1) return count - 1;
  return Math.min(count - 1, Math.floor(progress * count));
}
