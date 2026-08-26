import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { HERO_MESSAGES } from "@/lib/marketing/heroStrengths";
import { PRODUCT_NAME } from "@/lib/brand";

const REQUIRED_KEYS = [
  "id",
  "badge",
  "headlineLead",
  "headlineAccent",
  "tagline",
  "description",
] as const;

describe("HERO_MESSAGES", () => {
  it("ships seven distinct capability sets", () => {
    assert.equal(HERO_MESSAGES.length, 7);
    const ids = new Set(HERO_MESSAGES.map((message) => message.id));
    assert.equal(ids.size, HERO_MESSAGES.length);
  });

  it("each message has the full marketing shape", () => {
    for (const message of HERO_MESSAGES) {
      for (const key of REQUIRED_KEYS) {
        assert.ok(
          typeof message[key] === "string" && message[key].length > 0,
          `${message.id}.${key} is a non-empty string`,
        );
      }
    }
  });

  it("covers shipped product capabilities", () => {
    const ids = HERO_MESSAGES.map((message) => message.id);
    assert.deepEqual(ids, [
      "company-watch",
      "story-mode",
      "career-discovery",
      "ats-keywords",
      "ats-score",
      "cover-letters",
      "tracker",
    ]);
  });

  it("claims no fabricated metrics in user-facing copy", () => {
    for (const message of HERO_MESSAGES) {
      const copy = [
        message.badge,
        message.headlineLead,
        message.headlineAccent,
        message.tagline,
        message.description,
      ].join(" ");
      assert.doesNotMatch(copy, /\d+\s*%/);
      assert.doesNotMatch(copy, /guarantee/i);
      assert.ok(copy.length > 40, `${message.id} is substantive copy`);
    }
  });

  it("uses the canonical product name in descriptions", () => {
    for (const message of HERO_MESSAGES) {
      if (message.id === "company-watch") {
        assert.match(message.description, new RegExp(PRODUCT_NAME));
      }
    }
    const withProductName = HERO_MESSAGES.filter((message) =>
      message.description.includes(PRODUCT_NAME),
    );
    assert.ok(withProductName.length >= 5, "most capability blurbs name the product");
  });
});
