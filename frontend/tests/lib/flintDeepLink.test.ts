import assert from "node:assert/strict";
import test from "node:test";

import {
  buildFlintImportLink,
  FLINT_IMPORT_SCHEME,
  FLINT_OPEN_FALLBACK_MS,
} from "../../lib/flintDeepLink";

test("buildFlintImportLink produces a valid flint:// deep link", () => {
  const uuid = "550e8400-e29b-41d4-a716-446655440000";
  const url = buildFlintImportLink(uuid);
  assert.equal(url, `${FLINT_IMPORT_SCHEME}?token=${uuid}`);
  assert.ok(url.startsWith(`${FLINT_IMPORT_SCHEME}?token=`));
});

test("buildFlintImportLink percent-encodes tokens with special characters", () => {
  const token = "tok+en=val&ue";
  const url = buildFlintImportLink(token);
  const value = url.slice(url.indexOf("?token=") + 7);
  assert.ok(!value.includes("&"), "& must be encoded");
  assert.ok(!value.includes("="), "= must be encoded");
});

test("fallback window is 3 seconds", () => {
  assert.equal(FLINT_OPEN_FALLBACK_MS, 3000);
});
