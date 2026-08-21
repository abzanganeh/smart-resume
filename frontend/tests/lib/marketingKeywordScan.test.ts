import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  DEMO_JD_KEYWORDS,
  DEMO_RESUME_LINES,
  classifyKeywords,
  revealedCount,
} from "@/lib/marketing/keywordScan";

describe("classifyKeywords", () => {
  it("matches a keyword present in the resume, ignoring case", () => {
    const [result] = classifyKeywords("Built REST apis in Go", ["rest"]);
    assert.equal(result.term, "rest");
    assert.equal(result.status, "matched");
  });

  it("reports a keyword absent from the resume as missing", () => {
    const [result] = classifyKeywords("Built REST APIs in Go", ["Kubernetes"]);
    assert.equal(result.status, "missing");
  });

  it("requires a whole-token match so 'Java' does not match 'JavaScript'", () => {
    // The demo claims to show an ATS keyword audit. Substring matching would
    // overstate coverage and make the illustration dishonest.
    const [result] = classifyKeywords("Shipped JavaScript dashboards", ["Java"]);
    assert.equal(result.status, "missing");
  });

  it("matches a term containing punctuation, like CI/CD", () => {
    const [result] = classifyKeywords("Owned CI/CD pipelines", ["CI/CD"]);
    assert.equal(result.status, "matched");
  });

  it("matches a multi-word term", () => {
    const [result] = classifyKeywords("Led incident response drills", [
      "incident response",
    ]);
    assert.equal(result.status, "matched");
  });

  it("preserves keyword order so the sweep reveals them predictably", () => {
    const results = classifyKeywords("Go and SQL", ["SQL", "Go", "Rust"]);
    assert.deepEqual(
      results.map((r) => r.term),
      ["SQL", "Go", "Rust"],
    );
  });

  it("returns nothing for an empty keyword list", () => {
    assert.deepEqual(classifyKeywords("anything at all", []), []);
  });

  it("treats a blank or whitespace-only term as missing rather than matching everything", () => {
    // An empty needle trivially "appears" in any haystack; guard against it.
    const results = classifyKeywords("Built REST APIs", ["", "   "]);
    for (const result of results) {
      assert.equal(result.status, "missing");
    }
  });

  it("does not match across a line break as if it were one phrase", () => {
    const [result] = classifyKeywords("incident\nresponse", [
      "incident response",
    ]);
    assert.equal(result.status, "missing");
  });
});

describe("revealedCount", () => {
  it("reveals nothing before the sweep starts", () => {
    assert.equal(revealedCount(0, 5), 0);
  });

  it("reveals everything once the sweep completes", () => {
    assert.equal(revealedCount(1, 5), 5);
  });

  it("reveals proportionally mid-sweep", () => {
    assert.equal(revealedCount(0.5, 4), 2);
  });

  it("clamps progress outside the unit interval", () => {
    assert.equal(revealedCount(-3, 5), 0);
    assert.equal(revealedCount(42, 5), 5);
  });

  it("handles an empty keyword set without returning a negative count", () => {
    assert.equal(revealedCount(0.5, 0), 0);
  });
});

describe("demo fixtures", () => {
  it("ships sample data for both panes", () => {
    assert.ok(DEMO_RESUME_LINES.length > 0, "resume sample is non-empty");
    assert.ok(DEMO_JD_KEYWORDS.length > 0, "keyword sample is non-empty");
  });

  it("shows both matched and missing keywords so the demo is not a victory lap", () => {
    // A demo where everything matches teaches the visitor nothing about the
    // gap audit, which is the capability being illustrated.
    const results = classifyKeywords(
      DEMO_RESUME_LINES.join("\n"),
      DEMO_JD_KEYWORDS,
    );
    assert.ok(
      results.some((r) => r.status === "matched"),
      "at least one keyword matches",
    );
    assert.ok(
      results.some((r) => r.status === "missing"),
      "at least one keyword is missing",
    );
  });

  it("names no real employer in the sample resume", () => {
    // The no-fabrication rule forbids implying a real company relationship.
    const sample = DEMO_RESUME_LINES.join(" ");
    for (const employer of ["Google", "Amazon", "Meta", "Microsoft", "Apple"]) {
      assert.ok(
        !sample.includes(employer),
        `sample resume must not name ${employer}`,
      );
    }
  });
});
