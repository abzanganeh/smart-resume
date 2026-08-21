import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  STAGE_LETTERS,
  activeStageFromProgress,
  railProgress,
  stageLetter,
  stageTheme,
} from "@/lib/marketing/stageRail";
import { JOURNEY_STEPS } from "@/lib/marketing/journey";

describe("stageLetter", () => {
  it("labels the stages A through F, matching the six-stage journey", () => {
    assert.equal(stageLetter(0), "A");
    assert.equal(stageLetter(5), "F");
    assert.equal(STAGE_LETTERS.length, JOURNEY_STEPS.length);
  });

  it("falls back to a number past the letter range rather than throwing", () => {
    // The rail is decorative. A seventh stage must not blank the section.
    assert.equal(stageLetter(6), "7");
  });

  it("ignores a negative or non-integer index", () => {
    assert.equal(stageLetter(-1), "1");
    assert.equal(stageLetter(Number.NaN), "1");
  });
});

describe("stageTheme", () => {
  it("gives every journey stage its own colour", () => {
    const accents = JOURNEY_STEPS.map((step) => stageTheme(step.id).accent);
    assert.equal(new Set(accents).size, JOURNEY_STEPS.length);
  });

  it("returns usable classes for an unknown id instead of undefined", () => {
    const theme = stageTheme("not-a-stage");
    assert.ok(theme.text.length > 0);
    assert.ok(theme.dot.length > 0);
  });

  it("pairs a light and a dark class for text so contrast holds in both themes", () => {
    for (const step of JOURNEY_STEPS) {
      const { text } = stageTheme(step.id);
      assert.match(text, /dark:/, `${step.id} has a dark variant`);
    }
  });
});

describe("railProgress", () => {
  const VIEWPORT = 800;

  it("is zero before the section reaches the read line", () => {
    assert.equal(railProgress({ top: VIEWPORT, height: 1000 }, VIEWPORT), 0);
  });

  it("is one once the section has scrolled past", () => {
    assert.equal(railProgress({ top: -2000, height: 1000 }, VIEWPORT), 1);
  });

  it("is a half when the section midpoint sits on the read line", () => {
    // Read line is the viewport midpoint, so a 1000px section whose top is
    // 400 - 500 = -100 has its centre exactly on the line.
    assert.equal(railProgress({ top: -100, height: 1000 }, VIEWPORT), 0.5);
  });

  it("returns zero for a degenerate rect rather than dividing by zero", () => {
    assert.equal(railProgress({ top: 0, height: 0 }, VIEWPORT), 0);
    assert.equal(railProgress({ top: 0, height: -10 }, VIEWPORT), 0);
  });

  it("returns zero for non-finite input", () => {
    assert.equal(railProgress({ top: Number.NaN, height: 100 }, VIEWPORT), 0);
    assert.equal(railProgress({ top: 0, height: 100 }, Number.NaN), 0);
  });
});

describe("activeStageFromProgress", () => {
  it("selects the first stage at the start and the last at the end", () => {
    assert.equal(activeStageFromProgress(0, 6), 0);
    assert.equal(activeStageFromProgress(1, 6), 5);
  });

  it("advances one stage per equal slice of progress", () => {
    assert.equal(activeStageFromProgress(0.5, 6), 3);
  });

  it("returns null when there are no stages", () => {
    assert.equal(activeStageFromProgress(0.5, 0), null);
  });

  it("clamps progress outside the unit interval", () => {
    assert.equal(activeStageFromProgress(-1, 6), 0);
    assert.equal(activeStageFromProgress(9, 6), 5);
    assert.equal(activeStageFromProgress(Number.NaN, 6), 0);
  });
});
