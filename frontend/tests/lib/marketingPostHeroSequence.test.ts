import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { postHeroMotion } from "@/lib/marketing/postHeroSequence";

describe("postHeroMotion", () => {
  it("raises the CTA block from below first", () => {
    const start = postHeroMotion(0);
    const mid = postHeroMotion(0.08);
    assert.equal(start.cta.opacity, 0);
    assert.ok(mid.cta.opacity > start.cta.opacity);
    assert.ok(mid.cta.y < start.cta.y);
  });

  it("swaps CTA for roles left-to-right", () => {
    const before = postHeroMotion(0.25);
    const during = postHeroMotion(0.33);
    const after = postHeroMotion(0.45);
    assert.ok(before.cta.opacity > 0.9);
    assert.ok(during.roles.opacity > before.roles.opacity);
    assert.ok(after.roles.opacity > 0.9);
    assert.ok(after.cta.opacity < 0.1);
  });

  it("hands off to the journey intro after roles exit", () => {
    const late = postHeroMotion(0.75);
    assert.ok(late.journeyIntro.opacity > 0.9);
    assert.ok(late.roles.opacity < 0.1);
  });
});
