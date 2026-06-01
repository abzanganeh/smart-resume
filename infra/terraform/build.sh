#!/usr/bin/env bash
# Build minimal Lambda deployment zips for Terraform (handler only).
# Production deploys should bundle psycopg2-binary + boto3 into each zip or use layers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

for fn in apify_cache_worker job_cache_writer alert_dispatcher notification_scheduler; do
  zip -j "$BUILD/${fn}.zip" "$ROOT/../${fn}/handler.py"
  echo "built $BUILD/${fn}.zip"
done
