#!/usr/bin/env bash
# Boot local-sim desktop staging on host ports 3001/8001 (never 3000).
#
# Uses dummy Stripe IDs (setup-staging-env.py --local-sim) and Mailpit for
# verify-email smoke. For production-like local staging (real Stripe test +
# Resend), see STAGING.md §2 — do not use this script.
#
# Usage:
#   ./scripts/desktop-staging-local-sim-up.sh

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

FRONTEND_PORT=3001
BACKEND_PORT=8001

COMPOSE_FILES=(
  -f docker-compose.yml
  -f docker-compose.staging.yml
  -f docker-compose.local-sim.yml
)

die() {
  printf '\033[31m%s\033[0m\n' "ERROR: $*" >&2
  exit 1
}

warn() {
  printf '\033[33m%s\033[0m\n' "WARN: $*" >&2
}

if [ "${STAGING_FRONTEND_PORT:-$FRONTEND_PORT}" != "$FRONTEND_PORT" ] \
  || [ "${STAGING_BACKEND_PORT:-$BACKEND_PORT}" != "$BACKEND_PORT" ]; then
  die "Refusing non-default staging ports (require ${FRONTEND_PORT}/${BACKEND_PORT}; never bind host 3000 for FlintApply)."
fi

if [ -f .env.staging ] && [ ! -f backend/.env.staging ]; then
  die "Missing backend/.env.staging — run: python3 scripts/setup-staging-env.py --local-sim"
elif [ ! -f .env.staging ] && [ -f backend/.env.staging ]; then
  die "Missing .env.staging — run: python3 scripts/setup-staging-env.py --local-sim"
fi

if [ ! -f .env.staging ] || [ ! -f backend/.env.staging ]; then
  echo "Generating gitignored staging env files (--local-sim)..."
  python3 scripts/setup-staging-env.py --local-sim
  echo "Bootstrap admin password was printed above — save securely; do not commit."
fi

if ! python3 scripts/setup-staging-env.py --check; then
  warn "setup-staging-env.py --check reported gaps (e.g. missing LLM key). HTTP smoke may still pass; fill keys before AI features."
fi

if ! LOCAL_SIM_ENV_CHECK=1 ./scripts/production-preflight.sh; then
  die "Local-sim Stripe guard failed — remove sk_live_* from backend/.env.staging before workstation smoke."
fi

echo "Starting local-sim staging stack (ports ${FRONTEND_PORT}/${BACKEND_PORT})..."
STAGING_FRONTEND_PORT="$FRONTEND_PORT" STAGING_BACKEND_PORT="$BACKEND_PORT" \
  docker compose "${COMPOSE_FILES[@]}" up -d --build

echo
echo "=== Local-sim desktop staging ==="
echo "Frontend:  http://localhost:${FRONTEND_PORT}"
echo "API:       http://localhost:${BACKEND_PORT}"
echo "Mailpit:   http://127.0.0.1:38025"
echo
echo "Smoke:     API_URL=http://localhost:${BACKEND_PORT} FRONTEND_URL=http://localhost:${FRONTEND_PORT} ./scripts/staging-smoke.sh"
echo "Manual UI: STAGING.md §5"
echo
echo "Stripe billing plans check is expected to SKIP on local-sim (dummy price IDs)."
