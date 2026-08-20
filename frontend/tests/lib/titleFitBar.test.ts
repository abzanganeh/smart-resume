import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { titleFitBar, titleFitLabel } from "@/lib/jobs";

describe("titleFitBar", () => {
  it("renders filled and empty blocks from score", () => {
    const bar = titleFitBar(50, 10);
    assert.equal(bar.length, 10);
    assert.match(bar, /^█+░+$/);
    assert.equal(bar.split("█").length - 1, 5);
  });

  it("clamps scores to 0-100", () => {
    assert.equal(titleFitBar(150, 8), titleFitBar(100, 8));
    assert.equal(titleFitBar(-5, 8), titleFitBar(0, 8));
  });
});

describe("titleFitLabel", () => {
  it("formats percentage fit label", () => {
    assert.equal(titleFitLabel(94), "94% fit");
  });
});
