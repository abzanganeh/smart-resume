import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  STAGE_LETTERS,
  activeStageFromProgress,
  pinnedProgress,
  pinnedProgressForSticky,
  railProgress,
  stageLetter,
  stageTheme,
} from "@/lib/marketing/stageRail";
import { JOURNEY_STEPS } from "@/lib/marketing/journey";

describe("stageLetter", () => {
  it("labels the stages A through G, matching the seven-stage journey", () => {
    assert.equal(stageLetter(0), "A");
    assert.equal(stageLetter(6), "G");
    assert.equal(STAGE_LETTERS.length, JOURNEY_STEPS.length);
  });

  it("falls back to a number past the letter range rather than throwing", () => {
    // The rail is decorative. An eighth stage must not blank the section.
    assert.equal(stageLetter(7), "8");
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

describe("pinnedProgress", () => {
  const VIEWPORT = 800;
  // A 3x-viewport track, so 1600px of travel while the child stays pinned.
  const HEIGHT = 2400;

  it("is zero until the track reaches the top of the viewport", () => {
    // The bug this replaces: railProgress already reads ~0.29 here, so the
    // first stage was partly consumed before the visitor scrolled at all.
    assert.equal(pinnedProgress({ top: VIEWPORT, height: HEIGHT }, VIEWPORT), 0);
    assert.equal(pinnedProgress({ top: 0, height: HEIGHT }, VIEWPORT), 0);
  });

  it("is one when the track bottom reaches the viewport bottom", () => {
    assert.equal(
      pinnedProgress({ top: -(HEIGHT - VIEWPORT), height: HEIGHT }, VIEWPORT),
      1,
    );
  });

  it("is a half at the midpoint of the pinned travel", () => {
    assert.equal(pinnedProgress({ top: -800, height: HEIGHT }, VIEWPORT), 0.5);
  });

  it("clamps past the end of the track", () => {
    assert.equal(pinnedProgress({ top: -9000, height: HEIGHT }, VIEWPORT), 1);
  });

  it("resolves a track shorter than the viewport by which side of the fold it is on", () => {
    assert.equal(pinnedProgress({ top: 10, height: 200 }, VIEWPORT), 0);
    assert.equal(pinnedProgress({ top: -10, height: 200 }, VIEWPORT), 1);
  });

  it("returns zero for non-finite input rather than NaN", () => {
    assert.equal(
      pinnedProgress({ top: Number.NaN, height: HEIGHT }, VIEWPORT),
      0,
    );
    assert.equal(pinnedProgress({ top: 0, height: HEIGHT }, Number.NaN), 0);
  });
});

describe("pinnedProgressForSticky", () => {
  const VIEWPORT = 800;
  const STICKY_TOP = 64;
  const HEIGHT = 2400;

  it("is zero until the track reaches the sticky offset below the nav", () => {
    assert.equal(
      pinnedProgressForSticky({ top: STICKY_TOP + 100, height: HEIGHT }, VIEWPORT, STICKY_TOP),
      0,
    );
    assert.equal(
      pinnedProgressForSticky({ top: STICKY_TOP, height: HEIGHT }, VIEWPORT, STICKY_TOP),
      0,
    );
  });

  // Travel is divided as `height - viewportHeight`, so progress saturates once
  // the track has moved that far past the sticky line — one `stickyTop` before
  // the track bottom actually reaches the viewport bottom.
  it("reaches one at the end of the divided travel", () => {
    const travel = HEIGHT - VIEWPORT;
    assert.equal(
      pinnedProgressForSticky(
        { top: STICKY_TOP - travel, height: HEIGHT },
        VIEWPORT,
        STICKY_TOP,
      ),
      1,
    );
    assert.equal(
      pinnedProgressForSticky(
        { top: -(HEIGHT - VIEWPORT), height: HEIGHT },
        VIEWPORT,
        STICKY_TOP,
      ),
      1,
    );
  });

  it("clamps past the end of the track", () => {
    assert.equal(
      pinnedProgressForSticky({ top: -9000, height: HEIGHT }, VIEWPORT, STICKY_TOP),
      1,
    );
  });

  it("is a half at the midpoint of the divided travel", () => {
    const travel = HEIGHT - VIEWPORT;
    const midpointTop = STICKY_TOP - travel / 2;
    assert.equal(
      pinnedProgressForSticky({ top: midpointTop, height: HEIGHT }, VIEWPORT, STICKY_TOP),
      0.5,
    );
  });

  it("resolves a track shorter than the viewport by its side of the sticky line", () => {
    assert.equal(
      pinnedProgressForSticky({ top: STICKY_TOP - 1, height: 200 }, VIEWPORT, STICKY_TOP),
      1,
    );
    assert.equal(
      pinnedProgressForSticky({ top: STICKY_TOP + 1, height: 200 }, VIEWPORT, STICKY_TOP),
      0,
    );
  });

  it("returns zero for non-finite input", () => {
    assert.equal(
      pinnedProgressForSticky({ top: Number.NaN, height: HEIGHT }, VIEWPORT, STICKY_TOP),
      0,
    );
    assert.equal(
      pinnedProgressForSticky({ top: 0, height: Number.NaN }, VIEWPORT, STICKY_TOP),
      0,
    );
    assert.equal(
      pinnedProgressForSticky({ top: 0, height: HEIGHT }, Number.NaN, STICKY_TOP),
      0,
    );
    assert.equal(
      pinnedProgressForSticky({ top: 0, height: HEIGHT }, VIEWPORT, Number.NaN),
      0,
    );
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
