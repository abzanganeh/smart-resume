/**
 * Open in Flint button flow tests (Strategy B Phase 1.3).
 *
 * Simulates the async handoff + deep-link contract without a DOM renderer,
 * matching the pattern used by UsageWidget.test.tsx and flintDeepLink.test.ts.
 *
 * Run with: npm run test:unit
 */

import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFlintImportLink,
  FLINT_OPEN_FALLBACK_MS,
} from "../../lib/flintDeepLink";

type HandoffResult = { token: string };

async function simulateOpenInFlintFlow(options: {
  createHandoff: () => Promise<HandoffResult>;
  navigate: (deepLink: string) => void;
  hasFocus: () => boolean;
  schedule: (fn: () => void, delayMs: number) => void;
}): Promise<{ deepLink: string; showFallback: () => boolean; handoffCalls: number }> {
  let handoffCalls = 0;
  let showFallback = false;

  const { token } = await (async () => {
    handoffCalls += 1;
    return options.createHandoff();
  })();

  const deepLink = buildFlintImportLink(token);
  options.navigate(deepLink);

  options.schedule(() => {
    if (options.hasFocus()) {
      showFallback = true;
    }
  }, FLINT_OPEN_FALLBACK_MS);

  return { deepLink, showFallback: () => showFallback, handoffCalls };
}

test("calls handoff once and builds flint://import link", async () => {
  const navigated: string[] = [];

  const result = await simulateOpenInFlintFlow({
    createHandoff: async () => ({ token: "550e8400-e29b-41d4-a716-446655440000" }),
    navigate: (deepLink) => navigated.push(deepLink),
    hasFocus: () => false,
    schedule: () => {},
  });

  assert.equal(result.handoffCalls, 1);
  assert.equal(
    result.deepLink,
    "flint://import?token=550e8400-e29b-41d4-a716-446655440000",
  );
  assert.deepEqual(navigated, [result.deepLink]);
});

test("shows fallback hint when window still has focus after 3s", async () => {
  let scheduledDelay = -1;
  let scheduledFn: (() => void) | null = null;

  const result = await simulateOpenInFlintFlow({
    createHandoff: async () => ({ token: "abc-def-123" }),
    navigate: () => {},
    hasFocus: () => true,
    schedule: (fn, delayMs) => {
      scheduledDelay = delayMs;
      scheduledFn = fn;
    },
  });

  assert.equal(scheduledDelay, 3000);
  assert.equal(result.showFallback(), false);
  scheduledFn?.();
  assert.equal(result.showFallback(), true);
});

test("does not show fallback when Flint takes focus before timeout", async () => {
  let scheduledFn: (() => void) | null = null;

  const result = await simulateOpenInFlintFlow({
    createHandoff: async () => ({ token: "abc-def-123" }),
    navigate: () => {},
    hasFocus: () => false,
    schedule: (fn) => {
      scheduledFn = fn;
    },
  });

  scheduledFn?.();
  assert.equal(result.showFallback(), false);
});
