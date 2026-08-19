import { describe, it, before, after, afterEach } from "node:test"
import assert from "node:assert/strict"

import { formatMatchScore, matchJobs } from "@/lib/jobs"

let mockResponses: Array<{ status: number; body: unknown }> = []
let lastFetch: { url: string; init?: RequestInit } | null = null
const originalFetch = globalThis.fetch

before(() => {
  globalThis.fetch = ((url: string, init?: RequestInit) => {
    lastFetch = { url, init }
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
  lastFetch = null
})

after(() => {
  globalThis.fetch = originalFetch
})

describe("formatMatchScore", () => {
  it("formats fractional scores as percentages", () => {
    assert.equal(formatMatchScore(0.87), "87% match")
  })

  it("formats whole-number scores as percentages", () => {
    assert.equal(formatMatchScore(92), "92% match")
  })

  it("returns null for missing scores", () => {
    assert.equal(formatMatchScore(null), null)
    assert.equal(formatMatchScore(undefined), null)
  })
})

describe("matchJobs", () => {
  it("POSTs to /api/jobs/match with pagination", async () => {
    mockResponses.push({
      status: 200,
      body: {
        jobs: [{ id: "j1", title: "Engineer", company: "Acme", score: 0.91 }],
        total: 1,
        page: 2,
        page_size: 10,
        results_may_be_stale: false,
        message: null,
      },
    })

    const res = await matchJobs("tok", { page: 2, page_size: 10 })
    assert.equal(res.jobs[0]?.score, 0.91)
    assert.equal(res.page, 2)
    assert.ok(lastFetch?.url.endsWith("/api/jobs/match"))
    assert.equal(lastFetch?.init?.method, "POST")
    assert.deepEqual(JSON.parse(String(lastFetch?.init?.body)), {
      page: 2,
      page_size: 10,
    })
  })
})
