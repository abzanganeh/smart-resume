/**
 * Unit tests for admin session reason mapping and ModelPicker helpers.
 *
 * Run with: pnpm run test:unit
 */

import assert from "node:assert/strict"
import { describe, it } from "node:test"
import { renderToStaticMarkup } from "react-dom/server"
import {
  ModelPicker,
  defaultModelForProvider,
  resolveModelSelectValue,
} from "@/components/admin/ModelPicker"
import {
  adminAuthReasonMessage,
  adminAuthRedirectPathForSessionCode,
  mapAdminSessionGoneCodeToReason,
} from "@/lib/admin/session-reason"

const CATALOG = {
  openai: [
    { id: "gpt-4o-mini", label: "GPT-4o Mini", note: "Fast" },
    { id: "gpt-4o", label: "GPT-4o" },
  ],
  gemini: [{ id: "gemini-3.5-flash", label: "Gemini 3.5 Flash" }],
}

describe("mapAdminSessionGoneCodeToReason", () => {
  it("maps idle, expired, revoked, and binding mismatch", () => {
    assert.equal(mapAdminSessionGoneCodeToReason("admin_session_idle"), "idle")
    assert.equal(mapAdminSessionGoneCodeToReason("admin_session_expired"), "expired")
    assert.equal(
      mapAdminSessionGoneCodeToReason("admin_session_revoked"),
      "session_revoked",
    )
    assert.equal(
      mapAdminSessionGoneCodeToReason("admin_session_binding_mismatch"),
      "binding_mismatch",
    )
  })

  it("falls back to session_revoked for unknown codes", () => {
    assert.equal(mapAdminSessionGoneCodeToReason("admin_token_invalid"), "session_revoked")
    assert.equal(mapAdminSessionGoneCodeToReason("admin_unauthenticated"), "session_revoked")
  })

  it("builds layout redirect paths from backend codes", () => {
    assert.equal(
      adminAuthRedirectPathForSessionCode("admin_session_idle"),
      "/admin/auth?reason=idle",
    )
    assert.equal(
      adminAuthRedirectPathForSessionCode("admin_session_expired"),
      "/admin/auth?reason=expired",
    )
  })
})

describe("adminAuthReasonMessage", () => {
  it("returns distinct copy per reason", () => {
    const idle = adminAuthReasonMessage("idle") ?? ""
    const expired = adminAuthReasonMessage("expired") ?? ""
    const revoked = adminAuthReasonMessage("session_revoked") ?? ""
    const binding = adminAuthReasonMessage("binding_mismatch") ?? ""

    assert.match(idle, /15 minutes of inactivity/i)
    assert.match(expired, /60-minute/i)
    assert.match(revoked, /another browser/i)
    assert.match(binding, /network or browser/i)

    assert.doesNotMatch(idle, /60-minute/i)
    assert.doesNotMatch(expired, /15 minutes of inactivity/i)
    assert.notEqual(idle, revoked)
    assert.notEqual(revoked, binding)
  })

  it("returns null for unknown or missing reasons", () => {
    assert.equal(adminAuthReasonMessage(null), null)
    assert.equal(adminAuthReasonMessage("unknown"), null)
  })

  it("covers setup_password", () => {
    assert.match(adminAuthReasonMessage("setup_password") ?? "", /new password/i)
  })
})

describe("ModelPicker helpers", () => {
  it("resolveModelSelectValue uses catalog id or custom sentinel", () => {
    assert.equal(resolveModelSelectValue("openai", "gpt-4o", CATALOG), "gpt-4o")
    assert.equal(resolveModelSelectValue("openai", "my-custom", CATALOG), "__custom__")
    assert.equal(resolveModelSelectValue("gemini", "", CATALOG), "gemini-3.5-flash")
  })

  it("defaultModelForProvider keeps custom model when switching back", () => {
    assert.equal(defaultModelForProvider("gemini", CATALOG, "gpt-4o"), "gemini-3.5-flash")
    assert.equal(
      defaultModelForProvider("openai", CATALOG, "gpt-4o"),
      "gpt-4o",
    )
  })
})

describe("ModelPicker render", () => {
  it("renders catalog options with the selected model", () => {
    const catalogHtml = renderToStaticMarkup(
      <ModelPicker
        catalog={CATALOG}
        provider="openai"
        model="gpt-4o-mini"
        onProviderChange={() => {}}
        onModelChange={() => {}}
      />,
    )
    assert.match(catalogHtml, /selected=""[^>]*value="gpt-4o-mini"|value="gpt-4o-mini"[^>]*selected=""/)
    assert.match(catalogHtml, /Other \(custom id\)/)
    assert.match(catalogHtml, /Fast/)
  })

  it("renders custom model input when id is not in catalog", () => {
    const customHtml = renderToStaticMarkup(
      <ModelPicker
        catalog={CATALOG}
        provider="openai"
        model="vendor/special-model"
        onProviderChange={() => {}}
        onModelChange={() => {}}
      />,
    )
    assert.match(customHtml, /custom-model-id/)
    assert.match(customHtml, /value="vendor\/special-model"/)
    assert.match(customHtml, /selected=""[^>]*value="__custom__"|value="__custom__"[^>]*selected=""/)
  })
})

describe("ModelPicker provider change", () => {
  it("defaults to first catalog model when switching providers", () => {
    assert.equal(defaultModelForProvider("gemini", CATALOG, "gpt-4o-mini"), "gemini-3.5-flash")
    assert.equal(
      defaultModelForProvider("openai", CATALOG, "vendor/special-model"),
      "gpt-4o-mini",
    )
    assert.equal(resolveModelSelectValue("unknown", "x", {}), "__custom__")
  })
})
