#!/usr/bin/env bash
# Run pip-audit against uv.lock with a documented allowlist (OWASP A03 ratchet).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ALLOWLIST="${ROOT}/ci/pip-audit-allowlist.txt"
REQ=/tmp/requirements-audit.txt

cd "${ROOT}"
uv export --frozen --format requirements.txt --no-hashes --no-emit-project -o "${REQ}"

ignore_args=()
while IFS= read -r line || [[ -n "${line}" ]]; do
  line="${line%%#*}"
  line="$(echo "${line}" | xargs)"
  [[ -z "${line}" ]] && continue
  ignore_args+=(--ignore-vuln "${line}")
done < "${ALLOWLIST}"

uv tool run pip-audit -r "${REQ}" "${ignore_args[@]}"
