import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  JOURNEY_STEPS,
  journeyBadge,
  journeyStepById,
} from "@/lib/marketing/journey";

describe("JOURNEY_STEPS", () => {
  it("covers the six stages in order", () => {
    assert.equal(JOURNEY_STEPS.length, 6);
    assert.deepEqual(
      JOURNEY_STEPS.map((s) => s.step),
      [1, 2, 3, 4, 5, 6],
    );
  });

  it("uses unique ids", () => {
    const ids = new Set(JOURNEY_STEPS.map((s) => s.id));
    assert.equal(ids.size, JOURNEY_STEPS.length);
  });

  it("gives every step a contextual CTA pointing at an internal route", () => {
    for (const step of JOURNEY_STEPS) {
      assert.ok(step.ctaLabel.length > 0, `${step.id} has a CTA label`);
      assert.ok(step.ctaHref.startsWith("/"), `${step.id} CTA is internal`);
      assert.ok(step.title.length > 0, `${step.id} has a title`);
      assert.ok(step.description.length > 0, `${step.id} has a description`);
    }
  });

  it("avoids reusing one generic CTA label for every step", () => {
    const labels = new Set(JOURNEY_STEPS.map((s) => s.ctaLabel));
    assert.equal(labels.size, JOURNEY_STEPS.length);
    for (const step of JOURNEY_STEPS) {
      assert.notEqual(step.ctaLabel, "Create free account");
    }
  });
});

describe("journey access accuracy", () => {
  // These assertions are the honesty gate for the landing page: they pin the
  // marketing copy to what the backend actually gates.  If a route's gating
  // changes, this test should fail and force the badge to change with it.

  it("marks career discovery free — title-suggestions has no paid gate", () => {
    // backend/app/routers/jobs.py: get_title_suggestions depends only on
    // get_current_user (no _require_job_search_access, no quota charge).
    assert.equal(journeyStepById("discover").access, "free");
  });

  it("marks job search mixed — corpus is free, expanded search is paid", () => {
    // backend/app/routers/jobs.py:_require_job_search_access returns early for
    // subscribers and raises 402 only when expand=true for free users.
    assert.equal(journeyStepById("jobs").access, "mixed");
  });

  it("never marks a step paid without a badge to show for it", () => {
    for (const step of JOURNEY_STEPS) {
      if (step.access !== "free") {
        assert.ok(
          journeyBadge(step.access),
          `${step.id} is gated and must render a badge`,
        );
      }
    }
  });
});

describe("journeyBadge", () => {
  it("renders no badge for fully free stages", () => {
    assert.equal(journeyBadge("free"), null);
  });

  it("labels subscription-only stages", () => {
    assert.equal(journeyBadge("paid"), "Paid plans");
  });

  it("distinguishes partially free stages from fully paid ones", () => {
    const mixed = journeyBadge("mixed");
    assert.ok(mixed);
    assert.notEqual(mixed, journeyBadge("paid"));
    assert.match(mixed, /free/i);
  });
});

describe("credit disclosure", () => {
  it("notes the credit cost on every stage that spends credits", () => {
    // Story coaching, tailoring, and cover letters all debit credits on the
    // free plan (see FREE_TIER_CREDIT_ACTIONS). The journey subheading
    // promises that everything unbadged "works on the free tier", so each of
    // these has to say what it costs.
    for (const id of ["story", "tailor", "apply"]) {
      assert.ok(
        journeyStepById(id).accessNote,
        `${id} must disclose its credit cost`,
      );
    }
  });
});

describe("journeyStepById", () => {
  it("throws on an unknown id rather than returning undefined", () => {
    assert.throws(() => journeyStepById("nope"), /nope/);
  });
});
