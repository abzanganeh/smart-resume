import { describe, it } from "node:test";
import assert from "node:assert/strict";
import { ApiError } from "@/lib/api";
import { userFacingError } from "@/lib/userFacingError";

describe("userFacingError", () => {
  it("maps structured resume validation codes", () => {
    const err = new ApiError("too short", 422, "resume_too_short");
    assert.equal(userFacingError(err).message, "too short");
    assert.equal(userFacingError(err).code, "resume_too_short");
  });

  it("maps 402 provider credit errors", () => {
    const err = new ApiError("not enough credits", 402, "payment_required");
    const out = userFacingError(err);
    assert.match(out.message, /credits/i);
    assert.ok(out.helpUrl);
  });

  it("detects 402 phrasing in generic Error messages", () => {
    const out = userFacingError(new Error("OpenRouter 402: not enough credits"));
    assert.equal(out.code, "llm_insufficient_credits");
  });

  it("maps session_replaced to friendly copy", () => {
    const out = userFacingError(
      new ApiError("session_replaced", 401, "session_replaced"),
    );
    assert.match(out.message, /signed in somewhere else/i);
    assert.equal(out.code, "session_replaced");
  });
});
