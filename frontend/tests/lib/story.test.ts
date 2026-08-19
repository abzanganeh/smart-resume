/**
 * Tests for lib/story.ts — submitStory() API helper.
 *
 * Run: pnpm exec tsx tests/lib/story.test.ts
 */
import { submitStory } from "../../lib/story"

function assert(condition: boolean, message: string) {
  if (!condition) throw new Error(`FAIL: ${message}`)
  console.log(`  PASS: ${message}`)
}

async function runTests() {
  console.log("\nstory.ts submitStory() tests\n")

  const originalFetch = globalThis.fetch
  let capturedUrl = ""
  let capturedMethod = ""
  let capturedHeaders: Record<string, string> = {}
  let capturedBody = ""

  const mockResponse = {
    resume_text: "PROFESSIONAL SUMMARY\nEngineer\n",
    verify_items: [],
    verify_review_count: 0,
    billing: { charged_to: "first_story_generate", action: "story_build_generate" },
  };

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    capturedUrl = String(input)
    capturedMethod = init?.method ?? "GET"
    capturedHeaders = Object.fromEntries(
      Object.entries((init?.headers as Record<string, string>) ?? {}),
    )
    capturedBody = String(init?.body ?? "")
    return new Response(JSON.stringify(mockResponse), { status: 200 })
  }) as typeof fetch

  try {
    // Test 1: basic call
    const result = await submitStory(
      ["I worked at Acme Corp for 5 years building systems."],
      "test-token",
    )
    assert(capturedUrl.includes("/api/profile/resume/from-story"), "calls correct endpoint")
    assert(capturedMethod === "POST", "uses POST method")
    assert(capturedHeaders["Authorization"] === "Bearer test-token", "sends auth header")
    assert(capturedHeaders["Content-Type"] === "application/json", "sends JSON content type")
    const body = JSON.parse(capturedBody) as { segments: string[]; whisper_path: boolean }
    assert(body.whisper_path === false, "defaults whisper_path to false");
    assert(Array.isArray(body.segments), "sends segments array");
    assert(result.resume_text.includes("PROFESSIONAL SUMMARY"), "returns preview resume_text");
    assert(result.verify_review_count === 0, "returns verify_review_count");
    assert(result.billing.charged_to === "first_story_generate", "returns billing info");

    // Test 2: no BYOK headers
    await submitStory(
      ["Some career story text here."],
      "test-token",
    )
    assert(capturedHeaders["X-Api-Key"] === undefined, "does not send BYOK API key header")
    assert(capturedHeaders["X-Provider"] === undefined, "does not send BYOK provider header")
    assert(capturedHeaders["X-Model"] === undefined, "does not send BYOK model header")

    // Test 3: whisperPath flag
    await submitStory(["Some career story."], "test-token", { whisperPath: true })
    const bodyW = JSON.parse(capturedBody) as { whisper_path: boolean }
    assert(bodyW.whisper_path === true, "passes whisperPath=true as whisper_path")

    // Test 4: error handling
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: { message: "Story conversion failed" } }), { status: 502 })
    ) as typeof fetch

    let threw = false
    try {
      await submitStory(["Test."], "token")
    } catch (e) {
      threw = true
      assert(e instanceof Error && e.message === "Story conversion failed", "throws with server error message")
    }
    assert(threw, "throws on non-ok response")

    // Test 5: error handling with string detail
    globalThis.fetch = (async () =>
      new Response(JSON.stringify({ detail: "Unauthorized" }), { status: 401 })
    ) as typeof fetch

    let threw2 = false
    try {
      await submitStory(["Test."], "token")
    } catch (e) {
      threw2 = true
      assert(e instanceof Error && e.message === "Unauthorized", "handles string detail")
    }
    assert(threw2, "throws on 401")

    console.log("\nAll story lib tests passed ✓\n")
  } finally {
    globalThis.fetch = originalFetch
  }
}

runTests().catch((e: unknown) => {
  console.error(e instanceof Error ? e.message : e)
  process.exit(1)
})
