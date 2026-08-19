import { describe, it, before, after, afterEach } from "node:test"
import assert from "node:assert/strict"

import {
  createApplication,
  getApplicationFunnel,
  listApplications,
  TrackerApiError,
} from "@/lib/tracker"

// Stand up a global ``fetch`` stub so tracker.ts (which caches BASE from
// NEXT_PUBLIC_API_URL at import time) can be exercised without a network.

interface FetchCall {
  url: string
  init: RequestInit | undefined
}

let calls: FetchCall[] = []
let mockResponses: Array<{ status: number; body: unknown }> = []

const originalFetch = globalThis.fetch

before(() => {
  globalThis.fetch = ((input: RequestInfo | URL, init?: RequestInit) => {
    const url = typeof input === "string" ? input : input.toString()
    calls.push({ url, init })
    const next = mockResponses.shift()
    if (!next) throw new Error(`no mock response queued for ${url}`)
    return Promise.resolve({
      ok: next.status >= 200 && next.status < 300,
      status: next.status,
      json: async () => next.body,
    } as unknown as Response)
  }) as typeof fetch
})

afterEach(() => {
  calls = []
  mockResponses = []
})

after(() => {
  globalThis.fetch = originalFetch
})

describe("createApplication error surface", () => {
  it("throws TrackerApiError with tracker_limit_reached code on 409", async () => {
    mockResponses.push({
      status: 409,
      body: {
        detail: {
          code: "tracker_limit_reached",
          message: "cap hit",
          limit: 10,
          active_count: 10,
          plan_code: "free",
          resolution: "archive_or_upgrade",
        },
      },
    })

    try {
      await createApplication("tok", { jd_title: "PM", jd_company: "Co" })
      assert.fail("should throw")
    } catch (err) {
      assert.ok(err instanceof TrackerApiError)
      assert.equal(err.status, 409)
      assert.equal(err.code, "tracker_limit_reached")
      assert.equal(err.detail?.limit, 10)
    }
  })

  it("throws TrackerApiError with duplicate_application code on 409", async () => {
    mockResponses.push({
      status: 409,
      body: {
        detail: {
          code: "duplicate_application",
          message: "duplicate",
          existing_id: "abc-123",
          lookback_days: 30,
          resolution: "confirm_add_duplicate",
        },
      },
    })

    try {
      await createApplication("tok", { jd_title: "PM", jd_company: "Co" })
      assert.fail("should throw")
    } catch (err) {
      assert.ok(err instanceof TrackerApiError)
      assert.equal(err.code, "duplicate_application")
      assert.equal(err.detail?.existing_id, "abc-123")
    }
  })

  it("passes confirm_add_duplicate=true through to the backend", async () => {
    mockResponses.push({
      status: 201,
      body: {
        id: "new-id",
        resume_record_id: null,
        jd_title: "PM",
        jd_company: "Co",
        status: "draft",
        applied_date: null,
        follow_up_date: null,
        archived_at: null,
        created_at: "2026-08-19T00:00:00Z",
        updated_at: "2026-08-19T00:00:00Z",
      },
    })

    await createApplication("tok", {
      jd_title: "PM",
      jd_company: "Co",
      confirm_add_duplicate: true,
    })

    const body = JSON.parse((calls[0]?.init?.body as string) ?? "{}")
    assert.equal(body.confirm_add_duplicate, true)
  })

  it("still throws a plain Error message when the detail is a bare string", async () => {
    mockResponses.push({
      status: 500,
      body: { detail: "Internal Server Error" },
    })

    try {
      await createApplication("tok", { jd_title: "PM", jd_company: "Co" })
      assert.fail("should throw")
    } catch (err) {
      assert.ok(err instanceof TrackerApiError)
      assert.equal(err.status, 500)
      assert.equal(err.message, "Internal Server Error")
      assert.equal(err.code, undefined)
    }
  })
})

describe("listApplications archived filter", () => {
  it("sends archived=true as a query param", async () => {
    mockResponses.push({ status: 200, body: [] })

    await listApplications("tok", { archived: "true" })

    assert.match(calls[0].url, /\/api\/applications\?archived=true$/)
  })

  it("omits the query param when archived is not set", async () => {
    mockResponses.push({ status: 200, body: [] })

    await listApplications("tok")

    assert.match(calls[0].url, /\/api\/applications$/)
  })
})

describe("getApplicationFunnel", () => {
  it("hits /api/applications/funnel and returns typed payload", async () => {
    mockResponses.push({
      status: 200,
      body: {
        status_counts: {
          draft: 1,
          applied: 2,
          interviewing: 0,
          offer: 0,
          accepted: 0,
          rejected: 0,
          withdrawn: 0,
        },
        active_total: 3,
        archived_total: 1,
        total: 4,
        tracker_active_limit: 10,
      },
    })

    const funnel = await getApplicationFunnel("tok")
    assert.equal(funnel.total, 4)
    assert.equal(funnel.tracker_active_limit, 10)
    assert.match(calls[0].url, /\/api\/applications\/funnel$/)
  })
})
