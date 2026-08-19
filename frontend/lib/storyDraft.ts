/**
 * Persist an in-progress Story Mode draft so navigating away
 * (New Session, other profile tabs, refresh) does not lose spoken segments.
 *
 * Stored in localStorage — this is a local safety net, not the master resume.
 * Cleared after the user saves to their profile or discards the draft.
 */

export const STORY_DRAFT_STORAGE_KEY = "sr_story_draft";

const DRAFT_VERSION = 1;
const MAX_SEGMENTS = 30;
const MAX_SEGMENT_CHARS = 20_000;
const MAX_REVIEW_CHARS = 80_000;
const MAX_INTERVIEW_TURNS = 40;

export type StoryDraftMode = "free" | "interview";

export type StoryInterviewPhase =
  | "credit-disclosure"
  | "interviewing"
  | "complete"
  | "done";

export interface StoryInterviewTurn {
  role: "interviewer" | "user";
  text: string;
}

export interface StoryDraft {
  version: typeof DRAFT_VERSION;
  storyMode: StoryDraftMode | null;
  segments: string[];
  totalMs: number;
  reviewText: string | null;
  interviewHistory: StoryInterviewTurn[];
  interviewPhase: StoryInterviewPhase | null;
  interviewReviewText: string | null;
  updatedAt: number;
}

export function emptyStoryDraft(): StoryDraft {
  return {
    version: DRAFT_VERSION,
    storyMode: null,
    segments: [],
    totalMs: 0,
    reviewText: null,
    interviewHistory: [],
    interviewPhase: null,
    interviewReviewText: null,
    updatedAt: 0,
  };
}

export function hasMeaningfulStoryDraft(draft: StoryDraft | null): boolean {
  if (!draft) return false;
  return (
    draft.segments.some((s) => s.trim().length > 0) ||
    Boolean(draft.reviewText?.trim()) ||
    draft.interviewHistory.length > 0 ||
    Boolean(draft.interviewReviewText?.trim())
  );
}

function clampText(value: unknown, max: number): string {
  if (typeof value !== "string") return "";
  return value.length > max ? value.slice(0, max) : value;
}

function normalizeSegments(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((item): item is string => typeof item === "string")
    .map((item) => clampText(item, MAX_SEGMENT_CHARS))
    .filter((item) => item.trim().length > 0)
    .slice(0, MAX_SEGMENTS);
}

function normalizeInterviewHistory(value: unknown): StoryInterviewTurn[] {
  if (!Array.isArray(value)) return [];
  const turns: StoryInterviewTurn[] = [];
  for (const item of value) {
    if (!item || typeof item !== "object") continue;
    const role = (item as StoryInterviewTurn).role;
    const text = clampText((item as StoryInterviewTurn).text, MAX_SEGMENT_CHARS);
    if ((role === "interviewer" || role === "user") && text.trim()) {
      turns.push({ role, text });
    }
    if (turns.length >= MAX_INTERVIEW_TURNS) break;
  }
  return turns;
}

export function parseStoryDraft(raw: string | null): StoryDraft | null {
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<StoryDraft>;
    if (!parsed || parsed.version !== DRAFT_VERSION) return null;
    const storyMode =
      parsed.storyMode === "free" || parsed.storyMode === "interview"
        ? parsed.storyMode
        : null;
    const interviewPhase =
      parsed.interviewPhase === "credit-disclosure" ||
      parsed.interviewPhase === "interviewing" ||
      parsed.interviewPhase === "complete" ||
      parsed.interviewPhase === "done"
        ? parsed.interviewPhase
        : null;
    const totalMs =
      typeof parsed.totalMs === "number" && Number.isFinite(parsed.totalMs)
        ? Math.max(0, Math.min(parsed.totalMs, 30 * 60 * 1000))
        : 0;
    const reviewText = parsed.reviewText
      ? clampText(parsed.reviewText, MAX_REVIEW_CHARS)
      : null;
    const interviewReviewText = parsed.interviewReviewText
      ? clampText(parsed.interviewReviewText, MAX_REVIEW_CHARS)
      : null;
    return {
      version: DRAFT_VERSION,
      storyMode,
      segments: normalizeSegments(parsed.segments),
      totalMs,
      reviewText: reviewText?.trim() ? reviewText : null,
      interviewHistory: normalizeInterviewHistory(parsed.interviewHistory),
      interviewPhase,
      interviewReviewText: interviewReviewText?.trim() ? interviewReviewText : null,
      updatedAt: typeof parsed.updatedAt === "number" ? parsed.updatedAt : 0,
    };
  } catch {
    return null;
  }
}

function resolveStorage(storage?: Storage): Storage | null {
  if (storage) return storage;
  if (typeof window === "undefined") return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

export function loadStoryDraft(storage?: Storage): StoryDraft | null {
  const store = resolveStorage(storage);
  if (!store) return null;
  try {
    return parseStoryDraft(store.getItem(STORY_DRAFT_STORAGE_KEY));
  } catch {
    return null;
  }
}

export function saveStoryDraft(
  draft: StoryDraft,
  storage?: Storage,
): void {
  const store = resolveStorage(storage);
  if (!store) return;
  const next: StoryDraft = {
    ...emptyStoryDraft(),
    ...draft,
    version: DRAFT_VERSION,
    segments: normalizeSegments(draft.segments),
    interviewHistory: normalizeInterviewHistory(draft.interviewHistory),
    updatedAt: Date.now(),
  };
  try {
    store.setItem(STORY_DRAFT_STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Quota or private-mode — draft stays in memory only.
  }
}

export function patchStoryDraft(
  patch: Partial<StoryDraft>,
  storage?: Storage,
): StoryDraft {
  const current = loadStoryDraft(storage) ?? emptyStoryDraft();
  const next: StoryDraft = { ...current, ...patch };
  // Remount/HMR often patches empty initial state. Never let that erase a
  // committed draft — only clearStoryDraft() may wipe.
  if (
    Array.isArray(patch.segments) &&
    normalizeSegments(patch.segments).length === 0 &&
    current.segments.length > 0
  ) {
    next.segments = current.segments;
  }
  if (
    Array.isArray(patch.interviewHistory) &&
    normalizeInterviewHistory(patch.interviewHistory).length === 0 &&
    current.interviewHistory.length > 0
  ) {
    next.interviewHistory = current.interviewHistory;
  }
  saveStoryDraft(next, storage);
  return next;
}

export function clearStoryDraft(storage?: Storage): void {
  const store = resolveStorage(storage);
  if (!store) return;
  try {
    store.removeItem(STORY_DRAFT_STORAGE_KEY);
  } catch {
    // ignore
  }
}
