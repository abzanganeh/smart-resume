import { afterEach, describe, it, mock } from "node:test";
import assert from "node:assert/strict";
import {
  FREE_TIER_STARTING_CREDITS,
  fetchFreeTierStartingCredits,
} from "@/lib/freeTier";

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

  it("falls back to 3 when fetch fails", async () => {
    mock.method(globalThis, "fetch", async () => {
      throw new Error("network");
    });

    assert.equal(
      await fetchFreeTierStartingCredits(),
      FREE_TIER_STARTING_CREDITS,
    );
  });

  it("falls back to 3 when response is not ok", async () => {
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
