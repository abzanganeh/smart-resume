import { afterEach, describe, it, mock } from "node:test";
import assert from "node:assert/strict";
import {
  FREE_TIER_CREDIT_ACTIONS,
  FREE_TIER_STARTING_CREDITS,
  fetchFreeTierStartingCredits,
} from "@/lib/freeTier";

describe("FREE_TIER_CREDIT_ACTIONS", () => {
  it("matches backend free-tier quota debits", () => {
    const labels = FREE_TIER_CREDIT_ACTIONS.map((row) => row.action);
    assert.deepEqual(labels, [
      "Tailored rewrite",
      "QA & export (ATS score)",
      "Cover letter generation",
      "Coached story interview",
      "Story resume regenerate",
      "Story resume save",
    ]);
    assert.ok(
      !labels.some((label) => label.toLowerCase().includes("whisper")),
      "Whisper is gated to paid plans, not a free-tier credit price",
    );
  });
});

describe("FREE_TIER_STARTING_CREDITS", () => {
  it("matches the backend registration grant", () => {
    // The landing hero and signup copy render this number whenever
    // /api/billing/free-tier is unreachable, so a stale value advertises an
    // offer we do not honour.  Backend seed: tier_limits.py free
    // resumes_per_period = 3, asserted by
    // backend/tests/unit/test_tier_limits_config.py.
    assert.equal(FREE_TIER_STARTING_CREDITS, 3);
  });
});

describe("fetchFreeTierStartingCredits", () => {
  afterEach(() => {
    mock.restoreAll();
  });

  it("returns API value when fetch succeeds", async () => {
    mock.method(globalThis, "fetch", async () =>
      ({
        ok: true,
        json: async () => ({ starting_credits: 5 }),
      }) as Response,
    );

    assert.equal(await fetchFreeTierStartingCredits(), 5);
  });

  it("falls back to the seed constant when fetch fails", async () => {
    mock.method(globalThis, "fetch", async () => {
      throw new Error("network");
    });

    assert.equal(
      await fetchFreeTierStartingCredits(),
      FREE_TIER_STARTING_CREDITS,
    );
  });

  it("falls back to the seed constant when response is not ok", async () => {
    mock.method(globalThis, "fetch", async () =>
      ({
        ok: false,
      }) as Response,
    );

    assert.equal(
      await fetchFreeTierStartingCredits(),
      FREE_TIER_STARTING_CREDITS,
    );
  });
});
