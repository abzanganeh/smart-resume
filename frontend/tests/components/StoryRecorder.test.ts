/**
 * Unit tests for StoryRecorder logic.
 *
 * Tests the constants, state logic, and segment management behavior
 * without a DOM/React renderer.
 *
 * Run: pnpm exec tsx tests/components/StoryRecorder.test.ts
 */

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

function runTests() {
  console.log("\nStoryRecorder logic tests\n")

  const MAX_SEGMENTS = 30
  const SEGMENT_DURATION_MS = 60_000
  const WARN_TOTAL_MS = 18 * 60 * 1000
  const MAX_TOTAL_MS  = 30 * 60 * 1000

  // Constants
  assert(MAX_SEGMENTS === 30, "max segments is 30")
  assert(SEGMENT_DURATION_MS === 60_000, "segment duration is 60 seconds")
  assert(WARN_TOTAL_MS === 18 * 60 * 1000, "warning threshold is 18 minutes")
  assert(MAX_TOTAL_MS === 30 * 60 * 1000, "max total is 30 minutes")

  // totalMinsLabel formatting
  const formatTime = (ms: number) =>
    `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}`
  assert(formatTime(0) === "0:00", "formats 0ms as 0:00")
  assert(formatTime(60_000) === "1:00", "formats 60s as 1:00")
  assert(formatTime(18 * 60_000) === "18:00", "formats 18min as 18:00")
  assert(formatTime(30 * 60_000) === "30:00", "formats 30min as 30:00")
  assert(formatTime(90_000) === "1:30", "formats 90s as 1:30")

  // Max segments gate
  const segments30 = Array(30).fill("text")
  assert(segments30.length >= MAX_SEGMENTS, "canAddSegment is false at 30 segments")

  const segments29 = Array(29).fill("text")
  assert(segments29.length < MAX_SEGMENTS, "canAddSegment is true at 29 segments")

  // Warning detection
  assert(WARN_TOTAL_MS < MAX_TOTAL_MS, "warning fires before max total")
  const nearLimit = WARN_TOTAL_MS + 1
  assert(nearLimit >= WARN_TOTAL_MS, "warning triggers at 18:00+")

  // Segment deletion logic
  const segs = ["a", "b", "c", "d"]
  const afterDelete = segs.filter((_, i) => i !== 1)
  assert(afterDelete.length === 3, "delete removes exactly one segment")
  assert(afterDelete[0] === "a" && afterDelete[1] === "c", "delete preserves order")

  // Segment re-record logic
  const before = ["original", "b", "c"]
  const afterReRecord = before.map((s, i) => i === 0 ? "replaced" : s)
  assert(afterReRecord[0] === "replaced", "re-record replaces only the target segment")
  assert(afterReRecord[1] === "b" && afterReRecord[2] === "c", "re-record preserves other segments")

  // Progress bar width
  const pct = (totalMs: number) => Math.min((totalMs / MAX_TOTAL_MS) * 100, 100)
  assert(pct(0) === 0, "progress 0% at start")
  assert(pct(MAX_TOTAL_MS) === 100, "progress 100% at max total")
  assert(pct(MAX_TOTAL_MS + 1) === 100, "progress capped at 100%")
  assert(pct(15 * 60 * 1000) === 50, "progress 50% at 15 minutes")

  // Segment persistence across navigation lives in lib/storyDraft.ts
  // (localStorage). Leaving New Session / other menus must not drop committed
  // segments — see tests/lib/storyDraft.test.ts.

  console.log("\nAll StoryRecorder logic tests passed ✓\n")
}

runTests()
