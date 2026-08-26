/** Viewport height consumed by one hero message while the block stays pinned. */
export const HERO_SCROLL_SEGMENT_VH = 130;

/** Extra pinned scroll on the last hero slide before the CTA section releases. */
export const HERO_SCROLL_RELEASE_VH = 120;

/** Journey stages — scroll travel per letter while pinned. */
export const JOURNEY_SCROLL_SEGMENT_VH = 120;

/** Extra pinned scroll on the last journey stage before the section releases. */
export const JOURNEY_SCROLL_RELEASE_VH = 100;

/** Comparison crossfade track height (includes release tail). */
export const COMPARISON_SCROLL_TRACK_VH = 400;

/** Final slice of the comparison track holds on “With FlintApply” before release. */
export const COMPARISON_SCROLL_RELEASE_RATIO = 0.18;

/** Public nav is `h-16` and sticky; pinned panels sit beneath it. */
export const PINNED_STICKY_TOP_CLASS = "top-16";
export const PINNED_PANEL_HEIGHT_CLASS = "h-[calc(100dvh-4rem)]";
/** Matches `top-16` / public nav height — feed into pinned progress math. */
export const PINNED_STICKY_TOP_PX = 64;

export function heroScrollTrackHeightVh(messageCount: number): number {
  if (messageCount <= 0) return HERO_SCROLL_RELEASE_VH;
  return messageCount * HERO_SCROLL_SEGMENT_VH + HERO_SCROLL_RELEASE_VH;
}

/** Maps full-track progress (0–1) to message progress (0–1), excluding release tail. */
export function heroMessageProgressFromTrack(
  trackProgress: number,
  messageCount: number,
): number {
  if (messageCount <= 0) return 0;
  const total = heroScrollTrackHeightVh(messageCount);
  const messageShare = (messageCount * HERO_SCROLL_SEGMENT_VH) / total;
  if (!Number.isFinite(trackProgress) || trackProgress <= 0) return 0;
  if (trackProgress >= messageShare) return 1;
  return trackProgress / messageShare;
}

export function journeyScrollTrackHeightVh(stageCount: number): number {
  if (stageCount <= 0) return JOURNEY_SCROLL_RELEASE_VH;
  return stageCount * JOURNEY_SCROLL_SEGMENT_VH + JOURNEY_SCROLL_RELEASE_VH;
}

export function journeyStageProgressFromTrack(
  trackProgress: number,
  stageCount: number,
): number {
  if (stageCount <= 0) return 0;
  const total = journeyScrollTrackHeightVh(stageCount);
  const stageShare = (stageCount * JOURNEY_SCROLL_SEGMENT_VH) / total;
  if (!Number.isFinite(trackProgress) || trackProgress <= 0) return 0;
  if (trackProgress >= stageShare) return 1;
  return trackProgress / stageShare;
}

export function comparisonProgressFromTrack(trackProgress: number): number {
  const activeShare = 1 - COMPARISON_SCROLL_RELEASE_RATIO;
  if (!Number.isFinite(trackProgress) || trackProgress <= 0) return 0;
  if (trackProgress >= activeShare) return 1;
  return trackProgress / activeShare;
}
