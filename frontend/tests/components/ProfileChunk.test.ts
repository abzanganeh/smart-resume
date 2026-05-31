/**
 * Component tests for profile chunk save → PATCH /api/profile/resume/chunks/{id}.
 *
 * Run: pnpm exec tsx tests/components/ProfileChunk.test.ts
 */
import {
  buildPatchChunkUrl,
  formatEmbeddingCost,
  patchProfileChunk,
} from "../../lib/profile"

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

async function runTests() {
  console.log("\nProfile chunk PATCH tests\n")

  const chunkId = "11111111-2222-3333-4444-555555555555"
  const url = buildPatchChunkUrl(chunkId)
  assert(
    url.endsWith(`/api/profile/resume/chunks/${chunkId}`),
    "PATCH URL includes the chunk id",
  )

  assert(formatEmbeddingCost(100) === "< $0.001", "small token counts show < $0.001")

  const originalFetch = globalThis.fetch
  let capturedUrl = ""
  let capturedMethod = ""
  let capturedBody = ""

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    capturedUrl = String(input)
    capturedMethod = init?.method ?? "GET"
    capturedBody = String(init?.body ?? "")
    return new Response(
      JSON.stringify({
        chunk: {
          id: chunkId,
          section_type: "experience",
          content: "Updated bullet",
          token_count: 4,
          metadata: {},
          created_at: null,
          updated_at: null,
        },
      }),
      { status: 200, headers: { "Content-Type": "application/json" } },
    )
  }) as typeof fetch

  try {
    const updated = await patchProfileChunk("test-token", chunkId, "Updated bullet")
    assert(capturedMethod === "PATCH", "save triggers PATCH")
    assert(capturedUrl.includes(chunkId), "PATCH targets the correct chunk id")
    assert(capturedBody.includes("Updated bullet"), "PATCH body includes edited content")
    assert(updated.id === chunkId, "response chunk id matches")
  } finally {
    globalThis.fetch = originalFetch
  }

  console.log("\nAll profile chunk tests passed.\n")
}

if (typeof process !== "undefined" && process.argv[1]?.endsWith("ProfileChunk.test.ts")) {
  void runTests()
}

export { runTests }
