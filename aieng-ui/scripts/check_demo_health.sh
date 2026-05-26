#!/usr/bin/env bash
set -euo pipefail

# AIENG Demo Health Gate — local validation script.
# Usage:
#   ./scripts/check_demo_health.sh
#   ./scripts/check_demo_health.sh --full
#   ./scripts/check_demo_health.sh --frontend

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLATFORM_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
BACKEND_ROOT="${PLATFORM_ROOT}/backend"
FRONTEND_ROOT="${PLATFORM_ROOT}/frontend"

FAILED=0

run_step() {
  local label="$1"
  local workdir="$2"
  shift 2
  echo ""
  echo "==> ${label}"
  if (cd "${workdir}" && "$@"); then
    echo "OK: ${label}"
  else
    echo "FAIL: ${label}"
    FAILED=1
  fi
}

# Mandatory: smoke-check tests
run_step "Backend smoke-check tests" "${BACKEND_ROOT}" python -m pytest -q -k "smoke_check"

# Optional: full backend tests
if [[ "${1:-}" == "--full" ]]; then
  run_step "Full backend tests" "${BACKEND_ROOT}" python -m pytest -q
fi

# Optional: frontend build
if [[ "${1:-}" == "--frontend" || "${1:-}" == "--full" ]]; then
  run_step "Frontend build" "${FRONTEND_ROOT}" npm run build
fi

if [[ "${FAILED}" -eq 1 ]]; then
  echo ""
  echo "Demo health gate FAILED."
  exit 1
else
  echo ""
  echo "Demo health gate PASSED."
  exit 0
fi
