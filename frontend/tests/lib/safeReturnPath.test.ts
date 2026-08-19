import { describe, it } from "node:test"
import assert from "node:assert/strict"
import { safeReturnPath } from "@/app/jobs/setup/page"

describe("safeReturnPath", () => {
  it("allows single-slash internal paths", () => {
    assert.equal(safeReturnPath("/jobs"), "/jobs")
    assert.equal(safeReturnPath("/dashboard?foo=bar"), "/dashboard?foo=bar")
  })

  it("rejects protocol-relative URLs", () => {
    assert.equal(safeReturnPath("//evil.example"), "/jobs")
    assert.equal(safeReturnPath("/\\evil.example"), "/jobs")
  })

  it("rejects absolute URLs and other schemes", () => {
    assert.equal(safeReturnPath("https://evil.example/attack"), "/jobs")
    assert.equal(safeReturnPath("javascript:alert(1)"), "/jobs")
    assert.equal(safeReturnPath("data:text/html,foo"), "/jobs")
  })

  it("falls back on empty or missing input", () => {
    assert.equal(safeReturnPath(null), "/jobs")
    assert.equal(safeReturnPath(""), "/jobs")
    assert.equal(safeReturnPath("   "), "/jobs")
  })
})
