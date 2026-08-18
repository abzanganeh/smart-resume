#!/usr/bin/env bash
# Build minimal Lambda deployment zips for Terraform (handler only).
# Production deploys should bundle psycopg2-binary + boto3 into each zip or use layers.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
BUILD="$ROOT/build"
mkdir -p "$BUILD"

for fn in apify_cache_worker job_cache_writer alert_dispatcher notification_scheduler career_page_poller career_poll_worker career_matcher; do
  src_dir="$ROOT/../${fn}"
  if [ "$fn" = "career_poll_worker" ] && [ -f "$src_dir/adapters.py" ]; then
    (cd "$src_dir" && zip -j "$BUILD/${fn}.zip" handler.py adapters.py)
  else
    zip -j "$BUILD/${fn}.zip" "$src_dir/handler.py"
  fi
  echo "built $BUILD/${fn}.zip"
done
