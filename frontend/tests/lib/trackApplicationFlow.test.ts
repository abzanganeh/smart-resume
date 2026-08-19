import { describe, it, before, after, afterEach } from "node:test"
import assert from "node:assert/strict"

import {
  formatTrackerLimitError,
  trackApplicationWithDuplicatePrompt,
} from "@/lib/trackApplicationFlow"
import { TrackerApiError } from "@/lib/tracker"

let mockResponses: Array<{ status: number; body: unknown }> = []
const originalFetch = globalThis.fetch

before(() => {
  globalThis.fetch = (() => {
    const next = mockResponses.shift()
    if (!next) throw new Error("no mock response queued")
    return Promise.resolve({
      ok: next.status >= 200 && next.status < 300,
      status: next.status,
      json: async () => next.body,
    } as unknown as Response)
  }) as typeof fetch
})

afterEach(() => {
  mockResponses = []
})

after(() => {
  globalThis.fetch = originalFetch
})

describe("trackApplicationWithDuplicatePrompt", () => {
  it("retries with confirm_add_duplicate when user confirms", async () => {
    mockResponses.push(
      {
        status: 409,
        body: {
          detail: {
            code: "duplicate_application",
            message: "Already added",
            existing_id: "app-1",
          },
        },
      },
      {
        status: 201,
        body: {
          id: "app-2",
          jd_title: "PM",
          jd_company: "Co",
          status: "draft",
          archived_at: null,
        },
      },
    )

    const result = await trackApplicationWithDuplicatePrompt(
      "tok",
      { jd_title: "PM", jd_company: "Co", status: "draft" },
      () => true,
    )
    assert.equal(result.id, "app-2")
    assert.equal(mockResponses.length, 0)
  })

  it("rethrows duplicate when user declines", async () => {
    mockResponses.push({
      status: 409,
      body: {
        detail: {
          code: "duplicate_application",
          message: "Already added",
        },
      },
    })

    await assert.rejects(
      () =>
        trackApplicationWithDuplicatePrompt(
          "tok",
          { jd_title: "PM", jd_company: "Co", status: "draft" },
          () => false,
        ),
      (err: unknown) => err instanceof TrackerApiError && err.code === "duplicate_application",
    )
  })
})

describe("formatTrackerLimitError", () => {
  it("returns backend message without duplicate hint", () => {
    const msg = formatTrackerLimitError(
      new TrackerApiError(
        "You have reached your plan's active tracker limit of 10. Archive an existing application or upgrade your plan to add more.",
        {
          status: 409,
          code: "tracker_limit_reached",
        },
      ),
    )
    assert.equal(msg.includes("Archive an existing"), true)
    assert.equal((msg.match(/Archive/g) ?? []).length, 1)
  })
})
