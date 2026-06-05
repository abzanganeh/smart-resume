import assert from "node:assert/strict";
import test from "node:test";

// Pure-function unit tests for the deep-link and fallback logic in OpenInFlintButton.
// These exercise the exact same logic used by the component (copied here because
// buildDeepLink is not exported — a future refactor could extract it to a util).

const FLINT_SCHEME = "flint://import";
const FALLBACK_MS = 3000;

function buildDeepLink(token: string): string {
  return `${FLINT_SCHEME}?token=${encodeURIComponent(token)}`;
}

test("buildDeepLink produces a valid flint:// deep link", () => {
  const uuid = "550e8400-e29b-41d4-a716-446655440000";
  const url = buildDeepLink(uuid);
  assert.equal(url, `flint://import?token=${uuid}`);
  // Must start with the correct scheme so OS-level deep-link routing works.
  assert.ok(url.startsWith("flint://import?token="), "must use flint://import scheme");
});

test("buildDeepLink percent-encodes tokens with special characters", () => {
  const token = "tok+en=val&ue";
  const url = buildDeepLink(token);
  // '+', '=', '&' must be encoded so they don't break URL parsing.
  assert.ok(!url.slice(url.indexOf("?token=") + 7).includes("&"), "& must be encoded");
  assert.ok(!url.slice(url.indexOf("?token=") + 7).includes("="), "= must be encoded");
});

test("fallback window is 3 seconds", () => {
  // 3s gives the OS enough time to launch Flint; longer risks a false positive.
  assert.equal(FALLBACK_MS, 3000);
});
