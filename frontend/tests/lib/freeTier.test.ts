import { describe, expect, it, vi, afterEach } from "vitest";
import {
  FREE_TIER_STARTING_CREDITS,
  fetchFreeTierStartingCredits,
} from "@/lib/freeTier";

describe("fetchFreeTierStartingCredits", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("returns API value when fetch succeeds", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: true,
        json: async () => ({ starting_credits: 5 }),
      }),
    );

    await expect(fetchFreeTierStartingCredits()).resolves.toBe(5);
  });

  it("falls back to 3 when fetch fails", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network")));

    await expect(fetchFreeTierStartingCredits()).resolves.toBe(
      FREE_TIER_STARTING_CREDITS,
    );
  });

  it("falls back to 3 when response is not ok", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({
        ok: false,
      }),
    );

    await expect(fetchFreeTierStartingCredits()).resolves.toBe(
      FREE_TIER_STARTING_CREDITS,
    );
  });
});
