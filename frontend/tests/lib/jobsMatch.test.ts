import { describe, it, before, after, afterEach } from "node:test"
import assert from "node:assert/strict"

import { formatMatchScore, matchJobs } from "@/lib/jobs"

let mockResponses: Array<{ status: number; body: unknown }> = []
let lastFetch: { url: string; init?: RequestInit } | null = null
const originalFetch = globalThis.fetch
const OriginalBroadcastChannel = globalThis.BroadcastChannel

function hrefOf(input: RequestInfo | URL): string {
  if (typeof input === "string") return input
  if (input instanceof URL) return input.href
  return input.url
}

before(() => {
  // Node 20's BroadcastChannel keeps the test process alive after getSession().
  globalThis.BroadcastChannel = class {
    readonly name: string
    onmessage: ((ev: MessageEvent) => void) | null = null
    onmessageerror: ((ev: MessageEvent) => void) | null = null
    constructor(name: string) {
      this.name = name
    }
    postMessage(): void {}
    addEventListener(): void {}
    removeEventListener(): void {}
    close(): void {}
    dispatchEvent(): boolean {
      return false
    }
  } as unknown as typeof BroadcastChannel

  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const href = hrefOf(input)
    // next-auth getSession() fetches /api/auth/session before jobsRequest().
    if (href.includes("/api/auth/") || href.endsWith("/session")) {
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({}),
      } as unknown as Response)
    }
    lastFetch = { url: href, init }
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
  globalThis.BroadcastChannel = OriginalBroadcastChannel
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
