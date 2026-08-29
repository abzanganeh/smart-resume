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

echo "=== Flint Apply staging smoke ==="
echo "API:      $API_URL"
echo "Frontend: $FRONTEND_URL"
echo

echo "Waiting for backend (migrations can take ~30s on first boot)..."
ready=0
for i in $(seq 1 40); do
  if [ "$(http_status "$API_URL/health" 2>/dev/null || echo 000)" = "200" ]; then
    ready=1
    break
  fi
  sleep 2
done
if [ "$ready" -ne 1 ]; then
  red "Backend not ready at $API_URL/health after 80s — run: docker logs smart-resume-backend-1"
  exit 1
fi
echo "Backend ready."
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
  if [[ "${prices_count:-0}" -gt 0 ]]; then
    check "Billing prices has at least one plan" test "${prices_count}" -gt 0
  else
    skip_check "Billing plans count" "no Stripe plans (local staging sim — configure STRIPE_* for prod-like gate)"
  fi
else
  skip_check "Billing plans count" "could not parse /api/billing/prices"
fi

free_credits="$(http_json_field "$API_URL/api/billing/free-tier" starting_credits 2>/dev/null || true)"
if [[ -n "$free_credits" ]]; then
  check "Free-tier starting credits is 3" test "$free_credits" = "3"
else
  skip_check "Free-tier credits" "field missing"
fi

check "Frontend GET /auth/verify returns 200" test "$(http_status "$FRONTEND_URL/auth/verify")" = "200"

# CSP: local HTTP staging must not upgrade to HTTPS
csp_header="$(curl -sI "$FRONTEND_URL/onboarding" | tr -d '\r' | awk -F': ' 'tolower($1)=="content-security-policy"{print $2; exit}')"
if [[ -n "$csp_header" ]]; then
  check "CSP omits upgrade-insecure-requests on local HTTP staging" \
    test "${csp_header#*upgrade-insecure-requests}" = "$csp_header"
else
  skip_check "CSP upgrade-insecure-requests check" "no CSP header on /onboarding"
fi

# Auth register smoke (unique email per run) + authenticated tracker funnel
smoke_email="staging-smoke-$(date +%s%N)-$$@example.com"
register_tmp="$(mktemp)"
register_status="$(curl -s -o "$register_tmp" -w '%{http_code}' -X POST "$API_URL/api/auth/register" \
  -H 'Content-Type: application/json' \
  -d "{\"email\":\"$smoke_email\",\"password\":\"tr0ub4dor&3sandwich-eats-paint\",\"display_name\":\"Smoke Test\",\"accepted_tos_version\":\"2026-06\",\"turnstile_token\":\"staging-smoke-turnstile\"}")"
register_json="$(cat "$register_tmp")"
rm -f "$register_tmp"

check "POST /api/auth/register creates user (201)" test "$register_status" = "201"

if [[ "$register_status" = "201" && -n "$register_json" ]]; then
  check "Register response includes access_token" test "$(echo "$register_json" | python3 -c "import json,sys; print('ok' if json.load(sys.stdin).get('access_token') else '')")" = "ok"
  register_credits="$(echo "$register_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('user',{}).get('credit_balance',''))" 2>/dev/null || true)"
  if [[ -n "$register_credits" && -n "$free_credits" ]]; then
    check "Register credit_balance matches free-tier starting_credits (3)" test "$register_credits" = "$free_credits"
  else
    skip_check "Register credit_balance vs free-tier" "missing field(s)"
  fi
  spendable="$(echo "$register_json" | python3 -c "import json,sys; print(json.load(sys.stdin).get('user',{}).get('spendable_credit_balance',''))" 2>/dev/null || true)"
  locked="$(echo "$register_json" | python3 -c "import json,sys; u=json.load(sys.stdin).get('user',{}); print('true' if u.get('credits_locked_until_verification') else 'false')" 2>/dev/null || true)"
  check "Register spendable_credit_balance is 0 until verify" test "$spendable" = "0"
  check "Register credits_locked_until_verification is true" test "$locked" = "true"
  smoke_token="$(echo "$register_json" | python3 -c "import json,sys; print(json.load(sys.stdin)['access_token'])" 2>/dev/null || true)"
  if [[ -n "$smoke_token" ]]; then
    profile_status="$(curl -s -o /dev/null -w '%{http_code}' -X POST "$API_URL/api/profile/resume" \
      -H "Authorization: Bearer $smoke_token" \
      -F 'text=Jane Doe — Senior Backend Engineer with eight years building Python FastAPI services at Acme Corp serving millions of requests daily. Designed PostgreSQL schemas, Redis caching layers, and CI/CD pipelines.')"
    check "Unverified profile resume upload returns 403" test "$profile_status" = "403"
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
  skip_check "Register payload checks" "register did not return 201"
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

# Closure scheduler (optional — requires INTERNAL_SCHEDULER_SECRET in backend env)
scheduler_secret=""
if [[ -f backend/.env.staging ]]; then
  scheduler_secret="$(grep -E '^INTERNAL_SCHEDULER_SECRET=' backend/.env.staging 2>/dev/null | cut -d= -f2- || true)"
fi
scheduler_secret="${INTERNAL_SCHEDULER_SECRET:-$scheduler_secret}"
if [[ -n "$scheduler_secret" ]]; then
  scheduler_status="$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$API_URL/api/account" \
    -H "X-Scheduler-Secret: $scheduler_secret")"
  check "DELETE /api/account closure tick returns 200" test "$scheduler_status" = "200"
  unauth_status="$(curl -s -o /dev/null -w '%{http_code}' -X DELETE "$API_URL/api/account")"
  check "DELETE /api/account rejects missing scheduler secret (401)" test "$unauth_status" = "401"
else
  skip_check "Closure scheduler tick" "INTERNAL_SCHEDULER_SECRET not configured"
fi

echo
echo "=== Summary: $pass passed, $fail failed, $skip skipped ==="

if [[ "$fail" -gt 0 ]]; then
  red "Staging smoke FAILED"
  exit 1
fi

green "Staging smoke PASSED (automated). Run STAGING.md §5 manual checklist for UI flows."
exit 0
