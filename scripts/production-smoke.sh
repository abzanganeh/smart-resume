#!/usr/bin/env bash
# Production HTTP smoke — operator only. Registers real users on the target API.
#
# Usage:
#   CONFIRM_PRODUCTION_SMOKE=1 ./scripts/production-smoke.sh
#   CONFIRM_PRODUCTION_SMOKE=1 API_URL=https://api.example.com FRONTEND_URL=https://example.com ./scripts/production-smoke.sh

set -euo pipefail

if [[ "${CONFIRM_PRODUCTION_SMOKE:-}" != "1" ]]; then
  echo "Refusing to run production smoke without CONFIRM_PRODUCTION_SMOKE=1"
  echo "This script registers users on the live API — operator handoff only."
  exit 1
fi

API_URL="${API_URL:-https://api.flintapply.com}"
FRONTEND_URL="${FRONTEND_URL:-https://flintapply.com}"

if [[ "$API_URL" =~ ^https?://(localhost|127\.0\.0\.1)(:|/|$) ]]; then
  echo "Use ./scripts/staging-smoke.sh for localhost (REQUIRE_MAILPIT=1)."
  exit 1
fi

export API_URL FRONTEND_URL REQUIRE_MAILPIT=0
exec "$(dirname "$0")/staging-smoke.sh"
