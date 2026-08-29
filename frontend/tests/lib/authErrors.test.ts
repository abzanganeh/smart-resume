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

test("email_verification_required points users to verify before AI spend", () => {
  const msg = friendlyAuthError("email_verification_required")
  assert.match(msg, /verify your email/i)
  assert.doesNotMatch(msg, /reset link/i)
})

test("verify_token_expired and verify_token_invalid are distinct", () => {
  const expired = friendlyAuthError("verify_token_expired")
  const invalid = friendlyAuthError("verify_token_invalid")
  assert.match(expired, /expired/i)
  assert.match(invalid, /invalid/i)
  assert.notEqual(expired, invalid)
})

test("weak_password and signup_rate_limited have actionable copy", () => {
  assert.match(friendlyAuthError("weak_password"), /stronger password/i)
  assert.match(friendlyAuthError("signup_rate_limited"), /signups/i)
})

test("credits_locked_until_verification mentions unlocking credits", () => {
  assert.match(
    friendlyAuthError("credits_locked_until_verification"),
    /unlock/i,
  )
})
