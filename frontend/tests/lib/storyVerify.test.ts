/**
 * Unit tests for story verify/save credit labels.
 * Run: pnpm exec tsx tests/lib/storyVerify.test.ts
 */

import {
  storyGenerateCreditLabel,
  storySaveCreditLabel,
} from "../../lib/story";

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`);
  console.log(`  PASS: ${message}`);
}

function runTests() {
  console.log("\nstory verify billing label tests\n");

  assert(
    storyGenerateCreditLabel("first_story_generate", true) === "First generate free",
    "first generate free for free user",
  );
  assert(
    storyGenerateCreditLabel("free_credit", true) === "1 credit",
    "regenerate costs 1 credit",
  );
  assert(
    storySaveCreditLabel("first_story_save", true) === "First save free",
    "first save free for free user",
  );
  assert(
    storySaveCreditLabel("subscription", false) === "Included in your plan",
    "subscriber save included",
  );

  console.log("\nAll story verify billing label tests passed ✓\n");
}

runTests();
