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
