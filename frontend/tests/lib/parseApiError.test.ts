import { describe, it } from "node:test";
import assert from "node:assert/strict";
import {
  parseApiErrorDetail,
  SESSION_REPLACED_CODE,
} from "@/lib/parseApiError";

describe("parseApiErrorDetail", () => {
  it("maps session_replaced to friendly copy", () => {
    const out = parseApiErrorDetail({ code: SESSION_REPLACED_CODE }, 401);
    assert.equal(out.code, SESSION_REPLACED_CODE);
    assert.match(out.message, /signed in somewhere else/i);
    assert.doesNotMatch(out.message, /session_replaced/);
  });

  it("never returns a raw object as the message", () => {
    const out = parseApiErrorDetail({ code: SESSION_REPLACED_CODE }, 401);
    assert.equal(typeof out.message, "string");
    assert.notEqual(out.message, "[object Object]");
  });
});
