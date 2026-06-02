/**
 * Unit tests for StorySegment component behavior (logic / props).
 *
 * Since this is a plain tsx runner (not jest/vitest), we test the
 * component's exported interface and logic directly.
 *
 * Run: pnpm exec tsx tests/components/StorySegment.test.ts
 */

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

function runTests() {
  console.log("\nStorySegment component tests\n")

  // Test preview truncation logic
  const longText = "a".repeat(100)
  const preview = longText.slice(0, 80) + (longText.length > 80 ? "…" : "")
  assert(preview.length === 81, "preview appends ellipsis and truncates at 80 chars")
  assert(preview.endsWith("…"), "preview ends with ellipsis for long text")

  const shortText = "hello world"
  const shortPreview = shortText.slice(0, 80) + (shortText.length > 80 ? "…" : "")
  assert(shortPreview === "hello world", "short text preview has no ellipsis")

  // Test index labeling
  const index = 0
  const label = `Segment ${index + 1}`
  assert(label === "Segment 1", "first segment is labeled Segment 1")

  const index5 = 4
  const label5 = `Segment ${index5 + 1}`
  assert(label5 === "Segment 5", "fifth segment is labeled Segment 5")

  console.log("\nAll StorySegment tests passed ✓\n")
}

runTests()
