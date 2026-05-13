#!/usr/bin/env bash
set -euo pipefail

# Generic rollback helper. Intended for CI/CD integration.
# Usage: ./scripts/rollback.sh <target_ref>

TARGET_REF="${1:-}"
if [[ -z "${TARGET_REF}" ]]; then
  echo "Usage: $0 <target_ref>"
  exit 1
fi

echo "[rollback] switching to ${TARGET_REF}"
git fetch --all --tags
# Non-destructive checkout for deployment packaging context
if git rev-parse --verify "${TARGET_REF}" >/dev/null 2>&1; then
  git checkout "${TARGET_REF}"
else
  echo "Target ref not found: ${TARGET_REF}"
  exit 1
fi

echo "[rollback] target checked out successfully"
