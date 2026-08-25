import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { HERO_STRENGTHS } from "@/lib/marketing/heroStrengths";
import {
  HERO_STRENGTH_ROTATION_MS,
  nextStrengthIndex,
  resyncRotationClock,
  shouldAdvanceStrengthRotation,
} from "@/lib/marketing/heroStrengthRotation";

describe("HERO_STRENGTHS", () => {
  it("ships six distinct capability lines", () => {
    assert.equal(HERO_STRENGTHS.length, 6);
    const ids = new Set(HERO_STRENGTHS.map((item) => item.id));
    assert.equal(ids.size, HERO_STRENGTHS.length);
  });

  it("claims no fabricated metrics", () => {
    for (const strength of HERO_STRENGTHS) {
      assert.doesNotMatch(strength.line, /\d+\s*%/);
      assert.doesNotMatch(strength.line, /guarantee/i);
      assert.ok(strength.line.length > 20, `${strength.id} is substantive copy`);
    }
  });
});

describe("nextStrengthIndex", () => {
  it("wraps at the end of the list", () => {
    assert.equal(nextStrengthIndex(0, 6), 1);
    assert.equal(nextStrengthIndex(5, 6), 0);
  });

  it("returns zero for empty catalogs", () => {
    assert.equal(nextStrengthIndex(3, 0), 0);
  });
});

describe("shouldAdvanceStrengthRotation", () => {
  it("advances after the interval when active", () => {
    assert.equal(
      shouldAdvanceStrengthRotation({
        now: 10_500,
        lastAdvanceAt: 0,
        intervalMs: HERO_STRENGTH_ROTATION_MS,
        paused: false,
        documentHidden: false,
        count: 6,
      }),
      true,
    );
  });

  it("does not advance while paused, hidden, or on a single line", () => {
    const base = {
      now: 20_000,
      lastAdvanceAt: 0,
      intervalMs: HERO_STRENGTH_ROTATION_MS,
      count: 6,
    };
    assert.equal(
      shouldAdvanceStrengthRotation({ ...base, paused: true, documentHidden: false }),
      false,
    );
    assert.equal(
      shouldAdvanceStrengthRotation({ ...base, paused: false, documentHidden: true }),
      false,
    );
    assert.equal(
      shouldAdvanceStrengthRotation({ ...base, paused: false, documentHidden: false, count: 1 }),
      false,
    );
  });
});

describe("resyncRotationClock", () => {
  it("returns the current time for a finite value", () => {
    assert.equal(resyncRotationClock(42_000), 42_000);
    assert.equal(resyncRotationClock(Number.NaN), 0);
  });
});

describe("HERO_STRENGTH_ROTATION_MS", () => {
  it("rotates on a ten-second cadence", () => {
    assert.equal(HERO_STRENGTH_ROTATION_MS, 10_000);
  });
});
