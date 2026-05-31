/**
 * Component tests for JobsStaleBanner.
 *
 * Run: pnpm exec tsx tests/components/JobsStaleBanner.test.ts
 */
import { staleBannerMessage } from "../../lib/jobs"

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

export function runTests() {
  console.log("\nJobsStaleBanner component tests\n")

  assert(staleBannerMessage(false) === null, "stale=false → no banner message")
  assert(
    staleBannerMessage(true) === "Results may not be fully up to date",
    "stale=true without custom message → default copy",
  )
  assert(
    staleBannerMessage(true, "Custom stale notice") === "Results may not be fully up to date",
    "stale=true with custom message → still uses required exact copy",
  )
  assert(
    staleBannerMessage(true, "  ") === "Results may not be fully up to date",
    "stale=true with blank message → falls back to default",
  )
  assert(staleBannerMessage(false, "ignored") === null, "stale=false ignores message")

  console.log("\nAll tests passed.\n")
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("JobsStaleBanner.test.ts")) {
  runTests()
}

export { runTests as default }
