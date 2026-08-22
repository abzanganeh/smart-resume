import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  CAPABILITIES,
  capabilityById,
} from "@/lib/marketing/capabilities";
import { accessBadge } from "@/lib/marketing/journey";

describe("CAPABILITIES", () => {
  it("uses unique ids", () => {
    const ids = new Set(CAPABILITIES.map((c) => c.id));
    assert.equal(ids.size, CAPABILITIES.length);
  });

  it("gives every capability a title, a blurb, and a detail", () => {
    // Detail copy is rendered in every card — a missing string would leave a gap.
    for (const capability of CAPABILITIES) {
      assert.ok(capability.title.length > 0, `${capability.id} has a title`);
      assert.ok(capability.blurb.length > 0, `${capability.id} has a blurb`);
      assert.ok(capability.detail.length > 0, `${capability.id} has a detail`);
    }
  });

  it("says more in the detail than in the blurb", () => {
    // Otherwise the detail pane adds nothing and the interaction is decoration.
    for (const capability of CAPABILITIES) {
      assert.ok(
        capability.detail.length > capability.blurb.length,
        `${capability.id} detail must expand on its blurb`,
      );
      assert.notEqual(capability.detail, capability.blurb);
    }
  });

  it("never states gating without a badge to show for it", () => {
    for (const capability of CAPABILITIES) {
      if (capability.access && capability.access !== "free") {
        assert.ok(
          accessBadge(capability.access),
          `${capability.id} is gated and must render a badge`,
        );
      }
    }
  });
});

describe("capability gating accuracy", () => {
  // Same honesty gate as the journey model: these pin marketing copy to what
  // the backend actually enforces, so a gating change breaks the test rather
  // than silently shipping a false claim.

  it("marks job search mixed — corpus is free, expanded search is paid", () => {
    // backend/app/routers/jobs.py:_require_job_search_access raises 402 only
    // when expand=true for free users.
    assert.equal(capabilityById("job-search").access, "mixed");
  });

  it("marks fit scoring paid — there is no free allowance at all", () => {
    // backend/app/routers/fit.py:_require_fit_subscription raises 402 for every
    // non-subscriber, with no quota-based free tier.
    assert.equal(capabilityById("fit-score").access, "paid");
  });
});

describe("capabilityById", () => {
  it("throws on an unknown id rather than returning undefined", () => {
    assert.throws(() => capabilityById("nope"), /nope/);
  });
});
