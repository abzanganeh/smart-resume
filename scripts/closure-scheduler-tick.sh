#!/usr/bin/env bash
# Invoke the internal account-closure scheduler endpoint (day-23 reminders + due deletions).
#
# Usage:
#   ./scripts/closure-scheduler-tick.sh
#   API_URL=http://localhost:8001 INTERNAL_SCHEDULER_SECRET=... ./scripts/closure-scheduler-tick.sh
#
# Local staging compose runs this hourly via the ``closure-scheduler`` service.

set -euo pipefail

API_URL="${API_URL:-http://localhost:8001}"
SECRET="${INTERNAL_SCHEDULER_SECRET:-}"

if [[ -z "$SECRET" ]]; then
  echo "INTERNAL_SCHEDULER_SECRET is required" >&2
  exit 1
fi

curl -sf -X DELETE \
  -H "X-Scheduler-Secret: ${SECRET}" \
  "${API_URL}/api/account"
