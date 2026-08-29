#!/usr/bin/env bash
# Production deploy preflight — validates operator env before VM cutover.
# Does NOT deploy or hit live URLs unless PRODUCTION_ENV_CHECK=1 with files present.
#
# Usage:
#   ./scripts/production-preflight.sh
#   PRODUCTION_ENV_CHECK=1 ./scripts/production-preflight.sh

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
  else
    fail "backend/.env.staging has gaps (run: python3 scripts/setup-staging-env.py)"
  fi
else
  warn "backend/.env.staging missing — run: python3 scripts/setup-staging-env.py"
fi

check_https_var() {
  local name="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    warn "$name unset"
    return
  fi
  if [[ "$value" =~ ^https:// ]]; then
    ok "$name uses HTTPS"
  else
    fail "$name must be https:// for production ($value)"
  fi
}

if [[ "${PRODUCTION_ENV_CHECK:-0}" = "1" ]]; then
  root_env="${ROOT}/.env.staging"
  backend_env="${ROOT}/backend/.env.staging"
  if [[ ! -f "$root_env" || ! -f "$backend_env" ]]; then
    fail "PRODUCTION_ENV_CHECK=1 requires .env.staging and backend/.env.staging on disk"
  else
  # shellcheck disable=SC1090
    source <(grep -E '^(NEXTAUTH_URL|NEXT_PUBLIC_SITE_URL|NEXT_PUBLIC_API_URL|FRONTEND_BASE_URL)=' "$root_env" "$backend_env" 2>/dev/null | sed 's/^.*:\?//')
    check_https_var "NEXTAUTH_URL" "${NEXTAUTH_URL:-}"
    check_https_var "NEXT_PUBLIC_SITE_URL" "${NEXT_PUBLIC_SITE_URL:-}"
    check_https_var "NEXT_PUBLIC_API_URL" "${NEXT_PUBLIC_API_URL:-}"
    check_https_var "FRONTEND_BASE_URL" "${FRONTEND_BASE_URL:-}"
  fi
else
  warn "Skipping HTTPS env proof (set PRODUCTION_ENV_CHECK=1 after filling production URLs)"
fi

echo
echo "OAuth redirect URIs to register (production):"
echo "  https://flintapply.com/api/auth/callback/google"
echo "  https://flintapply.com/api/auth/callback/github"
echo "  https://flintapply.com/api/auth/callback/linkedin"
echo
echo "Stripe webhook: https://api.flintapply.com/api/billing/webhook"
echo "Reverse proxy: infra/caddy/Caddyfile.production.example"
echo

if [[ "$errors" -gt 0 ]]; then
  echo "Preflight FAILED ($errors issue(s))"
  exit 1
fi

echo "Preflight passed (operator must still run STAGING.md §8 deploy + §5 manual checklist)."
exit 0
