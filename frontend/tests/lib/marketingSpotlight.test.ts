import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  nearestIndex,
  normalizedPosition,
  shouldAnimate,
  tiltFor,
  type SpotlightRect,
} from "@/lib/marketing/spotlight";

const PANEL: SpotlightRect = { left: 0, top: 0, width: 200, height: 100 };

describe("normalizedPosition", () => {
  it("maps the centre of a rect to the middle of the unit square", () => {
    assert.deepEqual(normalizedPosition({ x: 100, y: 50 }, PANEL), {
      x: 0.5,
      y: 0.5,
    });
  });

  it("accounts for a rect that is not at the origin", () => {
    const offset: SpotlightRect = { left: 50, top: 20, width: 100, height: 40 };
    assert.deepEqual(normalizedPosition({ x: 100, y: 40 }, offset), {
      x: 0.5,
      y: 0.5,
    });
  });

  it("clamps a pointer outside the rect instead of extrapolating", () => {
    // The pointer can leave the panel between a pointermove and the next frame.
    // Unclamped values would push the spotlight gradient off the element.
    assert.deepEqual(normalizedPosition({ x: -500, y: -500 }, PANEL), {
      x: 0,
      y: 0,
    });
    assert.deepEqual(normalizedPosition({ x: 9999, y: 9999 }, PANEL), {
      x: 1,
      y: 1,
    });
  });

  it("returns the centre for a degenerate rect rather than dividing by zero", () => {
    const collapsed: SpotlightRect = { left: 0, top: 0, width: 0, height: 0 };
    const result = normalizedPosition({ x: 10, y: 10 }, collapsed);
    assert.ok(Number.isFinite(result.x), "x must be finite");
    assert.ok(Number.isFinite(result.y), "y must be finite");
    assert.deepEqual(result, { x: 0.5, y: 0.5 });
  });
});

describe("nearestIndex", () => {
  const cards: SpotlightRect[] = [
    { left: 0, top: 0, width: 100, height: 100 },
    { left: 200, top: 0, width: 100, height: 100 },
    { left: 400, top: 0, width: 100, height: 100 },
  ];

  it("picks the card whose centre is closest", () => {
    assert.equal(nearestIndex({ x: 20, y: 50 }, cards), 0);
    assert.equal(nearestIndex({ x: 240, y: 50 }, cards), 1);
    assert.equal(nearestIndex({ x: 460, y: 50 }, cards), 2);
  });

  it("still resolves a pointer in the gap between cards", () => {
    assert.equal(nearestIndex({ x: 160, y: 50 }, cards), 1);
  });

  it("resolves ties to the earlier card so selection is deterministic", () => {
    const equidistant: SpotlightRect[] = [
      { left: 0, top: 0, width: 100, height: 100 },
      { left: 100, top: 0, width: 100, height: 100 },
    ];
    assert.equal(nearestIndex({ x: 100, y: 50 }, equidistant), 0);
  });

  it("returns null when there are no cards to choose from", () => {
    assert.equal(nearestIndex({ x: 0, y: 0 }, []), null);
  });
});

describe("tiltFor", () => {
  it("applies no tilt at the exact centre", () => {
    assert.deepEqual(tiltFor({ x: 100, y: 50 }, PANEL, 6), {
      rotateX: 0,
      rotateY: 0,
    });
  });

  it("tilts in opposite directions on opposite edges", () => {
    const leftEdge = tiltFor({ x: 0, y: 50 }, PANEL, 6);
    const rightEdge = tiltFor({ x: 200, y: 50 }, PANEL, 6);
    assert.equal(leftEdge.rotateY, -rightEdge.rotateY);
    assert.notEqual(leftEdge.rotateY, 0);
  });

  it("never exceeds the maximum angle, even far outside the rect", () => {
    const far = tiltFor({ x: 99999, y: -99999 }, PANEL, 6);
    assert.ok(Math.abs(far.rotateX) <= 6, "rotateX within bound");
    assert.ok(Math.abs(far.rotateY) <= 6, "rotateY within bound");
  });

  it("produces a flat card when the maximum angle is zero", () => {
    assert.deepEqual(tiltFor({ x: 0, y: 0 }, PANEL, 0), {
      rotateX: 0,
      rotateY: 0,
    });
  });
});

describe("shouldAnimate", () => {
  it("animates only for a fine pointer with motion allowed", () => {
    assert.equal(
      shouldAnimate({ prefersReducedMotion: false, hasFinePointer: true }),
      true,
    );
  });

  it("refuses when the user asked for reduced motion", () => {
    assert.equal(
      shouldAnimate({ prefersReducedMotion: true, hasFinePointer: true }),
      false,
    );
  });

  it("refuses on touch, where there is no hover to follow", () => {
    assert.equal(
      shouldAnimate({ prefersReducedMotion: false, hasFinePointer: false }),
      false,
    );
  });
});
