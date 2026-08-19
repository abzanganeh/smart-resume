import { describe, it, beforeEach } from "node:test";
import assert from "node:assert/strict";
import {
  STORY_DRAFT_STORAGE_KEY,
  clearStoryDraft,
  emptyStoryDraft,
  hasMeaningfulStoryDraft,
  loadStoryDraft,
  parseStoryDraft,
  patchStoryDraft,
  saveStoryDraft,
  type StoryDraft,
} from "../../lib/storyDraft";

class MemoryStorage implements Storage {
  private data = new Map<string, string>();
  get length() {
    return this.data.size;
  }
  clear() {
    this.data.clear();
  }
  getItem(key: string) {
    return this.data.get(key) ?? null;
  }
  key(index: number) {
    return [...this.data.keys()][index] ?? null;
  }
  removeItem(key: string) {
    this.data.delete(key);
  }
  setItem(key: string, value: string) {
    this.data.set(key, value);
  }
}

function sampleDraft(overrides: Partial<StoryDraft> = {}): StoryDraft {
  return {
    ...emptyStoryDraft(),
    storyMode: "free",
    segments: ["I work at Northline Health.", "Before that BrightCart."],
    totalMs: 90_000,
    updatedAt: 1,
    ...overrides,
  };
}

describe("storyDraft", () => {
  let storage: MemoryStorage;

  beforeEach(() => {
    storage = new MemoryStorage();
  });

  it("round-trips committed segments so leaving the page does not drop them", () => {
    saveStoryDraft(sampleDraft(), storage);
    const loaded = loadStoryDraft(storage);
    assert.ok(loaded);
    assert.equal(loaded.storyMode, "free");
    assert.deepEqual(loaded.segments, [
      "I work at Northline Health.",
      "Before that BrightCart.",
    ]);
    assert.equal(loaded.totalMs, 90_000);
    assert.equal(hasMeaningfulStoryDraft(loaded), true);
  });

  it("treats empty drafts as not meaningful", () => {
    assert.equal(hasMeaningfulStoryDraft(null), false);
    assert.equal(hasMeaningfulStoryDraft(emptyStoryDraft()), false);
    assert.equal(
      hasMeaningfulStoryDraft(sampleDraft({ segments: ["   "], storyMode: "free" })),
      false,
    );
  });

  it("patches without wiping the other mode's progress", () => {
    saveStoryDraft(sampleDraft(), storage);
    patchStoryDraft(
      {
        interviewHistory: [{ role: "user", text: "I led a team of six." }],
        interviewPhase: "interviewing",
      },
      storage,
    );
    const loaded = loadStoryDraft(storage);
    assert.equal(loaded?.segments.length, 2);
    assert.equal(loaded?.interviewHistory[0]?.text, "I led a team of six.");
  });

  it("clears the draft after an explicit discard", () => {
    saveStoryDraft(sampleDraft(), storage);
    clearStoryDraft(storage);
    assert.equal(loadStoryDraft(storage), null);
    assert.equal(storage.getItem(STORY_DRAFT_STORAGE_KEY), null);
  });

  it("rejects corrupt or unknown-version payloads", () => {
    assert.equal(parseStoryDraft("not-json"), null);
    assert.equal(parseStoryDraft(JSON.stringify({ version: 99, segments: ["x"] })), null);
    assert.equal(parseStoryDraft(null), null);
  });

  it("does not let an empty remount patch wipe committed segments", () => {
    saveStoryDraft(sampleDraft(), storage);
    patchStoryDraft({ storyMode: null, segments: [], reviewText: null }, storage);
    const loaded = loadStoryDraft(storage);
    assert.equal(loaded?.segments.length, 2);
    assert.equal(loaded?.segments[0], "I work at Northline Health.");
  });

  it("drops blank segments and caps the list at 30", () => {
    const parsed = parseStoryDraft(
      JSON.stringify({
        version: 1,
        storyMode: "free",
        segments: ["keep", "  ", "", ...Array(40).fill("extra")],
        totalMs: 1000,
      }),
    );
    assert.ok(parsed);
    assert.equal(parsed.segments[0], "keep");
    assert.equal(parsed.segments.includes(""), false);
    assert.equal(parsed.segments.length, 30);
  });
});
