import assert from "node:assert/strict"
import test from "node:test"
import { friendlyAuthError } from "../../lib/auth/errors.ts"

test("Configuration explains host mismatch in local dev", () => {
  const msg = friendlyAuthError("Configuration")
  assert.match(msg, /host/i)
  assert.match(msg, /localhost/i)
})

test("OAuthBackendSyncPending mentions API reachability", () => {
  const msg = friendlyAuthError("OAuthBackendSyncPending")
  assert.match(msg, /API/i)
})

test("reset_token_expired tells the user to request a new link", () => {
  const msg = friendlyAuthError("reset_token_expired")
  assert.match(msg, /expired/i)
  assert.match(msg, /new one/i)
})

test("reset_token_invalid tells the user to request a new link", () => {
  const msg = friendlyAuthError("reset_token_invalid")
  assert.match(msg, /invalid/i)
})
