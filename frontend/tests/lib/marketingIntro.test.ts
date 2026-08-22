import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  INTRO_EMERGE_MS,
  INTRO_GREETING,
  INTRO_MOTION,
  INTRO_SIZE_SCALE,
  INTRO_TIMING,
  INTRO_TOTAL_MS,
  introMotionAt,
  introPhaseAt,
  introPhaseProgress,
  shouldPlayIntro,
} from "@/lib/marketing/intro";

describe("shouldPlayIntro", () => {
  it("plays for a first-time visitor who has not asked for reduced motion", () => {
    assert.equal(
      shouldPlayIntro({ prefersReducedMotion: false, alreadyPlayed: false }),
      true,
    );
  });

  it("never plays under an explicit reduced-motion request", () => {
    assert.equal(
      shouldPlayIntro({ prefersReducedMotion: true, alreadyPlayed: false }),
      false,
    );
  });

  it("plays once per session, not on every navigation", () => {
    assert.equal(
      shouldPlayIntro({ prefersReducedMotion: false, alreadyPlayed: true }),
      false,
    );
  });
});

describe("introPhaseAt", () => {
  it("runs logo-in, wordmark-in, greeting-in, hold, then done", () => {
    assert.equal(introPhaseAt(0), "logo-in");
    assert.equal(introPhaseAt(INTRO_TIMING.logoInMs - 1), "logo-in");
    assert.equal(introPhaseAt(INTRO_TIMING.logoInMs), "wordmark-in");
    assert.equal(
      introPhaseAt(INTRO_TIMING.logoInMs + INTRO_TIMING.wordmarkInMs - 1),
      "wordmark-in",
    );
    assert.equal(introPhaseAt(INTRO_EMERGE_MS - INTRO_TIMING.greetingInMs), "greeting-in");
    assert.equal(introPhaseAt(INTRO_EMERGE_MS - 1), "greeting-in");
    assert.equal(introPhaseAt(INTRO_EMERGE_MS), "hold");
    assert.equal(introPhaseAt(INTRO_TOTAL_MS - 1), "hold");
    assert.equal(introPhaseAt(INTRO_TOTAL_MS), "done");
  });

  it("treats negative or non-finite elapsed time as the first phase", () => {
    assert.equal(introPhaseAt(-50), "logo-in");
    assert.equal(introPhaseAt(Number.NaN), "logo-in");
  });

  it("totals twelve seconds: three three-second emerges plus a three-second hold", () => {
    assert.equal(INTRO_TOTAL_MS, 12_000);
    assert.equal(INTRO_EMERGE_MS, 9_000);
    assert.equal(INTRO_TIMING.logoInMs, 3_000);
    assert.equal(INTRO_TIMING.wordmarkInMs, 3_000);
    assert.equal(INTRO_TIMING.greetingInMs, 3_000);
    assert.equal(INTRO_TIMING.holdMs, 3_000);
  });
});

describe("introPhaseProgress", () => {
  it("is zero at each phase boundary start and approaches one at each phase end", () => {
    assert.equal(introPhaseProgress(0), 0);
    assert.equal(introPhaseProgress(INTRO_TIMING.logoInMs), 0);
    assert.ok(introPhaseProgress(INTRO_TIMING.logoInMs - 1) > 0.99);
    assert.equal(introPhaseProgress(INTRO_EMERGE_MS), 0);
    assert.ok(introPhaseProgress(INTRO_EMERGE_MS - 1) > 0.99);
  });
});

describe("introMotionAt", () => {
  it("starts the icon small and transparent", () => {
    const start = introMotionAt(0);
    assert.equal(start.phase, "logo-in");
    assert.equal(start.logoMark.opacity, 0);
    assert.equal(start.logoMark.scale, INTRO_MOTION.logoMarkStartScale);
    assert.equal(start.wordmark.opacity, 0);
    assert.equal(start.greeting.opacity, 0);
  });

  it("keeps the icon visible once the wordmark phase begins", () => {
    const wordmarkStart = introMotionAt(INTRO_TIMING.logoInMs);
    assert.equal(wordmarkStart.phase, "wordmark-in");
    assert.equal(wordmarkStart.logoMark.opacity, 1);
    assert.equal(wordmarkStart.logoMark.scale, INTRO_MOTION.logoMarkEndScale);
    assert.equal(wordmarkStart.wordmark.opacity, 0);
  });

  it("keeps the logo and wordmark visible once the greeting phase begins", () => {
    const greetingStart = introMotionAt(INTRO_EMERGE_MS - INTRO_TIMING.greetingInMs);
    assert.equal(greetingStart.phase, "greeting-in");
    assert.equal(greetingStart.logoMark.opacity, 1);
    assert.equal(greetingStart.wordmark.opacity, 1);
    assert.equal(greetingStart.greeting.opacity, 0);
  });

  it("holds all three layers at full opacity during the hold phase", () => {
    const hold = introMotionAt(INTRO_EMERGE_MS + 500);
    assert.equal(hold.phase, "hold");
    assert.equal(hold.logoMark.opacity, 1);
    assert.equal(hold.wordmark.opacity, 1);
    assert.equal(hold.greeting.opacity, 1);
    assert.equal(hold.logoMark.scale, 1);
    assert.equal(hold.wordmark.scale, 1);
    assert.equal(hold.greeting.scale, 1);
  });

  it("reveals the greeting over three seconds", () => {
    const afterEmerge = introMotionAt(INTRO_EMERGE_MS);
    assert.equal(afterEmerge.phase, "hold");
    assert.equal(afterEmerge.greeting.opacity, 1);
    assert.equal(afterEmerge.greeting.scale, INTRO_MOTION.greetingEndScale);
    assert.equal(INTRO_SIZE_SCALE, 2);
    assert.equal(afterEmerge.logoMark.opacity, 1);
    assert.equal(afterEmerge.wordmark.opacity, 1);
  });
});

describe("INTRO_GREETING", () => {
  it("introduces the product by name", () => {
    assert.match(INTRO_GREETING.line, /FlintApply/);
  });

  it("says what the product does rather than only who it is", () => {
    const text = `${INTRO_GREETING.line} ${INTRO_GREETING.sub}`.toLowerCase();
    assert.ok(text.includes("resume"), "mentions the resume");
    assert.ok(text.includes("job"), "mentions the job search");
  });

  it("claims no metric it cannot back up", () => {
    const text = `${INTRO_GREETING.line} ${INTRO_GREETING.sub}`;
    assert.doesNotMatch(text, /\d+\s*%/, "no invented percentages");
    assert.doesNotMatch(text, /guarantee/i, "no outcome guarantee");
  });
});
