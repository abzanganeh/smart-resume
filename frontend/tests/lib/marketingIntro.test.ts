import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  INTRO_GREETING,
  INTRO_LOGO_MS,
  INTRO_TOTAL_MS,
  introPhaseAt,
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
    // A full-viewport zoom is exactly the motion this preference exists to stop.
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
  it("shows the logo first", () => {
    assert.equal(introPhaseAt(0), "logo");
    assert.equal(introPhaseAt(INTRO_LOGO_MS - 1), "logo");
  });

  it("moves to the greeting after the logo settles", () => {
    assert.equal(introPhaseAt(INTRO_LOGO_MS), "greeting");
    assert.equal(introPhaseAt(INTRO_TOTAL_MS - 1), "greeting");
  });

  it("is done at the end, so the overlay can never trap the visitor", () => {
    assert.equal(introPhaseAt(INTRO_TOTAL_MS), "done");
    assert.equal(introPhaseAt(INTRO_TOTAL_MS + 10_000), "done");
  });

  it("treats negative or non-finite elapsed time as the first phase", () => {
    assert.equal(introPhaseAt(-50), "logo");
    assert.equal(introPhaseAt(Number.NaN), "logo");
  });

  it("finishes quickly enough not to be a barrier", () => {
    // A splash a visitor cannot skip past in a couple of seconds costs more
    // conversions than it wins.
    assert.ok(INTRO_TOTAL_MS <= 2_600, "intro is at most 2.6s");
    assert.ok(INTRO_LOGO_MS < INTRO_TOTAL_MS);
  });
});

describe("INTRO_GREETING", () => {
  it("introduces the product by name", () => {
    assert.match(INTRO_GREETING.line, /TalioCV/);
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
