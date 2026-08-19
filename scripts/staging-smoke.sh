#!/usr/bin/env bash
# Automated staging smoke checks (HTTP/curl). Manual UI flows remain in STAGING.md §5.
#
# Usage:
#   ./scripts/staging-smoke.sh
#   API_URL=https://staging-api.example.com FRONTEND_URL=https://staging.example.com ./scripts/staging-smoke.sh
#
# Exit 0 when all automated checks pass.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8001}"
FRONTEND_URL="${FRONTEND_URL:-http://localhost:3001}"

pass=0
fail=0
skip=0

green() { printf '\033[32m%s\033[0m\n' "$*"; }
red() { printf '\033[31m%s\033[0m\n' "$*"; }
yellow() { printf '\033[33m%s\033[0m\n' "$*"; }

check() {
  local name="$1"
  shift
  if "$@"; then
    green "PASS  $name"
    pass=$((pass + 1))
  else
    red "FAIL  $name"
    fail=$((fail + 1))
  fi
}

skip_check() {
  yellow "SKIP  $1 — $2"
  skip=$((skip + 1))
}

http_status() {
  curl -sf -o /dev/null -w '%{http_code}' "$@"
}

http_json_field() {
  curl -sf "$@" | python3 -c "import json,sys; d=json.load(sys.stdin); print(d.get('$2',''))"
}

echo "=== TalioCV staging smoke ==="
echo "API:      $API_URL"
echo "Frontend: $FRONTEND_URL"
echo

check "Backend /health returns 200" test "$(http_status "$API_URL/health")" = "200"

check "Frontend home returns 200" test "$(http_status "$FRONTEND_URL/")" = "200"

check "GET /api/billing/prices returns 200" test "$(http_status "$API_URL/api/billing/prices")" = "200"

check "GET /api/billing/free-tier returns 200" test "$(http_status "$API_URL/api/billing/free-tier")" = "200"

check "GET /api/feature-flags returns 200" test "$(http_status "$API_URL/api/feature-flags")" = "200"

check "Checkup rejects empty resume (422)" test "$(http_status -X POST "$API_URL/api/checkup" \
  -H 'Content-Type: application/json' \
  -d '{"resume_text":"","job_title":"Software Engineer","jd_text":"We need Python and AWS experience for this role."}')" = "422"

check "Checkup rejects short JD (422)" test "$(http_status -X POST "$API_URL/api/checkup" \
  -H 'Content-Type: application/json' \
  -d '{"resume_text":"'"$(python3 -c 'print("x"*250)')"'","job_title":"Engineer","jd_text":"short"}')" = "422"

# Price gap probe — plans array should be non-empty when Stripe is configured
if prices_count="$(curl -sf "$API_URL/api/billing/prices" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('plans',[])))" 2>/dev/null)"; then
  check "Billing prices has at least one plan" test "${prices_count:-0}" -gt 0
else
  skip_check "Billing plans count" "could not parse /api/billing/prices"
fi

free_credits="$(http_json_field "$API_URL/api/billing/free-tier" starting_credits 2>/dev/null || true)"
if [[ -n "$free_credits" ]]; then
  check "Free-tier starting credits is 6 (PR #76 grant bump)" test "$free_credits" = "6"
else
  skip_check "Free-tier credits" "field missing"
fi

# Auth register smoke (unique email per run) + authenticated tracker funnel
smoke_email="staging-smoke-$(date +%s)@example.com"
register_json="$(curl -sf -X POST "$API_URL/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$smoke_email\",\"password\":\"StagingSmoke1!\",\"display_name\":\"Smoke Test\",\"accepted_tos_version\":\"2026-01\"}" 2>/dev/null || true)"
if [[ -n "$register_json" ]]; then
  check "POST /api/auth/register creates user (201)" test "$(echo "$register_json" | python3 -c "import json,sys; print('ok' if json.load(sys.stdin).get('access_token') else '')")" = "ok"
  register_credits="$(echo "$register_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('user',{}).get('credit_balance',''))" 2>/dev/null || true)"
  if [[ -n "$register_credits" ]]; then
    check "Register grants 6 starting credits" test "$register_credits" = "6"
  else
    skip_check "Register credit_balance" "field missing on user payload"
  fi
  smoke_token="$(echo "$register_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || true)"
  if [[ -n "$smoke_token" ]]; then
    funnel_status="$(http_status -H "Authorization: Bearer $smoke_token" "$API_URL/api/applications/funnel")"
    check "GET /api/applications/funnel returns 200 (auth)" test "$funnel_status" = "200"
    funnel_limit="$(curl -sf -H "Authorization: Bearer $smoke_token" "$API_URL/api/applications/funnel" | python3 -c "import json,sys; print(json.load(sys.stdin).get('tracker_active_limit',''))" 2>/dev/null || true)"
    if [[ -n "$funnel_limit" ]]; then
      check "Funnel exposes free-tier tracker_active_limit=10" test "$funnel_limit" = "10"
    else
      skip_check "Funnel tracker_active_limit" "field missing"
    fi
  else
    skip_check "Authenticated funnel" "could not parse access_token"
  fi
else
  register_status="$(http_status -X POST "$API_URL/api/auth/register" \
    -H 'Content-Type: application/json' \
    -d "{\"email\":\"$smoke_email\",\"password\":\"StagingSmoke1!\",\"display_name\":\"Smoke Test\",\"accepted_tos_version\":\"2026-01\"}")"
  check "POST /api/auth/register creates user (201)" test "$register_status" = "201"
fi

# Frontend legal pages (CI e2e subset)
for path in /legal/privacy /legal/terms /checkup; do
  check "Frontend GET $path returns 200" test "$(http_status "$FRONTEND_URL$path")" = "200"
done

# OAuth providers endpoint (NextAuth)
if providers="$(curl -sf "$FRONTEND_URL/api/auth/providers" 2>/dev/null)"; then
  if echo "$providers" | grep -q '"credentials"'; then
    green "PASS  NextAuth credentials provider registered"
    pass=$((pass + 1))
  else
    red "FAIL  NextAuth credentials provider registered"
    fail=$((fail + 1))
  fi
else
  skip_check "NextAuth providers" "frontend /api/auth/providers unreachable"
fi

echo
echo "=== Summary: $pass passed, $fail failed, $skip skipped ==="

if [[ "$fail" -gt 0 ]]; then
  red "Staging smoke FAILED"
  exit 1
fi

green "Staging smoke PASSED (automated). Run STAGING.md §5 manual checklist for UI flows."
exit 0
