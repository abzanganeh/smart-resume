#!/usr/bin/env bash
# Production deploy preflight — validates operator env before VM cutover.
# Does NOT deploy or hit live URLs unless PRODUCTION_ENV_CHECK=1 with files present.
#
# Usage:
#   ./scripts/production-preflight.sh
#   PRODUCTION_ENV_CHECK=1 ./scripts/production-preflight.sh
#   LOCAL_SIM_ENV_CHECK=1 ./scripts/production-preflight.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== Flint Apply production preflight ==="
errors=0

warn() { printf '\033[33mWARN  %s\033[0m\n' "$*"; }
fail() { printf '\033[31mFAIL  %s\033[0m\n' "$*"; errors=$((errors + 1)); }
ok() { printf '\033[32mOK    %s\033[0m\n' "$*"; }

if [[ -f backend/.env.staging ]]; then
  if python3 scripts/setup-staging-env.py --check; then
    ok "backend/.env.staging passes setup-staging-env.py --check"
  elif [[ "${LOCAL_SIM_ENV_CHECK:-0}" = "1" ]]; then
    warn "backend/.env.staging has gaps (local-sim may still boot; fill keys before AI features)"
  else
    fail "backend/.env.staging has gaps (run: python3 scripts/setup-staging-env.py)"
  fi
else
  warn "backend/.env.staging missing — run: python3 scripts/setup-staging-env.py"
fi

if [[ "${PRODUCTION_ENV_CHECK:-0}" = "1" ]]; then
  root_env="${ROOT}/.env.staging"
  backend_env="${ROOT}/backend/.env.staging"
  if [[ ! -f "$root_env" || ! -f "$backend_env" ]]; then
    fail "PRODUCTION_ENV_CHECK=1 requires .env.staging and backend/.env.staging on disk"
  else
    while IFS= read -r line; do
      case "$line" in
        FAIL:*)
          fail "${line#FAIL: }"
          ;;
        OK:*)
          ok "${line#OK: }"
          ;;
        WARN:*)
          warn "${line#WARN: }"
          ;;
      esac
    done < <(
      python3 - "$root_env" "$backend_env" <<'PY'
import sys
from pathlib import Path

keys = (
    "NEXTAUTH_URL",
    "NEXT_PUBLIC_SITE_URL",
    "NEXT_PUBLIC_API_URL",
    "FRONTEND_BASE_URL",
    "RESEND_API_KEY",
    "SIGNUP_IP_DAILY_LIMIT",
    "STRIPE_SECRET_KEY",
)
values: dict[str, str] = {}
root_stripe = ""
backend_stripe = ""
for path in sys.argv[1:]:
    is_backend = Path(path).parent.name == "backend"
    for raw in Path(path).read_text().splitlines():
        if not raw or raw.lstrip().startswith("#") or "=" not in raw:
            continue
        key, _, val = raw.partition("=")
        key = key.strip()
        val = val.strip().strip('"').strip("'")
        if key == "STRIPE_SECRET_KEY":
            if is_backend:
                backend_stripe = val
            else:
                root_stripe = val
        if key in keys and key not in values:
            values[key] = val

if root_stripe:
    print("FAIL:STRIPE_SECRET_KEY must not be set in .env.staging (backend/.env.staging only)")

url_keys = (
    "NEXTAUTH_URL",
    "NEXT_PUBLIC_SITE_URL",
    "NEXT_PUBLIC_API_URL",
    "FRONTEND_BASE_URL",
)
https_prod = False
for key in url_keys:
    val = values.get(key, "")
    if not val:
        print(f"FAIL:{key} unset")
    elif not val.startswith("https://"):
        print(f"FAIL:{key} must use HTTPS (got {val})")
    else:
        print(f"OK:{key} uses HTTPS")
        https_prod = True

signup = values.get("SIGNUP_IP_DAILY_LIMIT", "")
if signup and signup != "15":
    print(f"FAIL:SIGNUP_IP_DAILY_LIMIT must be 15 on production VM (got {signup})")

resend = values.get("RESEND_API_KEY", "")
if not resend or resend.endswith("...") or resend == "change-me-in-production":
    print("FAIL:RESEND_API_KEY missing or placeholder — verification email requires Resend on VM")
elif resend:
    print("OK:RESEND_API_KEY configured")

stripe = backend_stripe or values.get("STRIPE_SECRET_KEY", "")
if https_prod and not stripe:
    print("FAIL:STRIPE_SECRET_KEY unset on production HTTPS deploy")
elif https_prod and stripe.startswith("sk_test_"):
    print("FAIL:STRIPE_SECRET_KEY must not be sk_test_* on production HTTPS deploy")
elif https_prod and stripe.startswith("sk_live_"):
    print("OK:STRIPE_SECRET_KEY uses live key for production")
PY
    )
  fi
else
  warn "Skipping HTTPS env proof (set PRODUCTION_ENV_CHECK=1 after filling production URLs)"
fi

if [[ "${LOCAL_SIM_ENV_CHECK:-0}" = "1" ]]; then
  backend_env="${ROOT}/backend/.env.staging"
  if [[ ! -f "$backend_env" ]]; then
    fail "LOCAL_SIM_ENV_CHECK=1 requires backend/.env.staging on disk"
  else
    while IFS= read -r line; do
      case "$line" in
        FAIL:*)
          fail "${line#FAIL: }"
          ;;
        OK:*)
          ok "${line#OK: }"
          ;;
      esac
    done < <(
      python3 - "$backend_env" <<'PY'
import sys
from pathlib import Path

stripe = ""
for raw in Path(sys.argv[1]).read_text().splitlines():
    if not raw or raw.lstrip().startswith("#") or "=" not in raw:
        continue
    key, _, val = raw.partition("=")
    if key.strip() == "STRIPE_SECRET_KEY":
        stripe = val.strip().strip('"').strip("'")
        break

if stripe.startswith("sk_live_"):
    print("FAIL:STRIPE_SECRET_KEY must not be sk_live_* in local-sim (use sk_test_local_staging_sim)")
elif stripe:
    print("OK:STRIPE_SECRET_KEY is not a live key (local-sim)")
else:
    print("FAIL:STRIPE_SECRET_KEY unset in backend/.env.staging")
PY
    )
  fi
fi

echo
echo "OAuth redirect URIs to register (production):"
echo "  https://flintapply.com/api/auth/callback/google"
echo "  https://flintapply.com/api/auth/callback/github"
echo "  https://flintapply.com/api/auth/callback/linkedin"
echo
echo "Stripe webhook: https://api.flintapply.com/api/billing/webhook"
echo "Reverse proxy: infra/caddy/Caddyfile.production.example"
echo "Local smoke only: add -f docker-compose.local-sim.yml (not for VM/production)"
echo

if [[ "$errors" -gt 0 ]]; then
  echo "Preflight FAILED ($errors issue(s))"
  exit 1
fi

echo "Preflight passed (operator must still run STAGING.md §8 deploy + §5 manual checklist)."
exit 0
